/* Diagnostico manual de uma pagina publica, sem cookies pessoais ou servidor. */
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const pasta = path.resolve('test-results/dnit-ao-vivo');
fs.mkdirSync(pasta, { recursive: true });
const pagina = 'https://servicos.dnit.gov.br/multas/informacoes/equipamentos-fiscalizacao';
const urlPublica = url => { try { const u = new URL(url); return u.origin + u.pathname; } catch { return ''; } };

(async () => {
  const relatorio = { pagina, iniciado_em: new Date().toISOString(), rede: [], erros_javascript: [], falhas: [] };
  const proxy = process.env.HTTPS_PROXY || process.env.https_proxy || process.env.HTTP_PROXY || process.env.http_proxy;
  const browser = await chromium.launch({ headless: true, ...(proxy ? { proxy: { server: proxy } } : {}) });
  const page = await browser.newPage();
  const pendentes = [];
  let scripts = 0;
  page.on('pageerror', e => relatorio.erros_javascript.push(String(e).slice(0, 3000)));
  page.on('requestfailed', r => relatorio.falhas.push({ url: urlPublica(r.url()), erro: r.failure()?.errorText }));
  page.on('response', response => {
    if (relatorio.rede.length < 150) relatorio.rede.push({ status: response.status(), tipo: response.request().resourceType(), url: urlPublica(response.url()) });
    // Fontes Javascript publicos do proprio portal ajudam a identificar a API
    // de dados. Nao guardar headers, cookies ou corpos de requisicoes.
    if (response.request().resourceType() === 'script' && new URL(response.url()).hostname === 'servicos.dnit.gov.br' && scripts < 12) {
      const arquivo = `script-${scripts++}.js`;
      pendentes.push(response.body().then(b => { if (b.length <= 5000000) fs.writeFileSync(path.join(pasta, arquivo), b); }).catch(() => {}));
    }
  });
  try {
    await page.goto(pagina, { waitUntil: 'domcontentloaded', timeout: 45000 });
    await page.waitForTimeout(7000);
    relatorio.titulo = await page.title();
    relatorio.texto = (await page.locator('body').innerText()).slice(0, 20000);
    relatorio.controles = await page.locator('button,a,[role="button"]').evaluateAll(es => es.filter(e => e.getClientRects().length).map(e => ({ texto: e.innerText, titulo: e.title, aria: e.getAttribute('aria-label') })).slice(0, 60));
    await page.screenshot({ path: path.join(pasta, 'pagina.png'), fullPage: true });
  } catch (e) { relatorio.erro_navegacao = String(e); }
  finally {
    await Promise.allSettled(pendentes);
    await browser.close();
    fs.writeFileSync(path.join(pasta, 'pagina.json'), JSON.stringify(relatorio, null, 2));
  }
  // O download e a validacao sao feitos pelo mesmo conector da instalacao,
  // usando um navegador novo. Nao importar fixtures nem escrever na base real.
  const bin = path.join(pasta, 'bin');
  fs.mkdirSync(bin, { recursive: true });
  fs.symlinkSync(chromium.executablePath(), path.join(bin, 'chromium'));
  const resultado = spawnSync('python', ['-c', `
import hashlib,json,pathlib
from coletor.fontes.dnit import ColetorDNITEquipamentos
pasta=pathlib.Path(${JSON.stringify(pasta)})
c=ColetorDNITEquipamentos()
corpo,ext,mime,registros=c.carregar(c.PAGINA)
for i,r in enumerate(registros): c.normalizar(i,r)
(pasta/'TabelaEquipamentosFiscalizacao.xlsx').write_bytes(corpo)
print(json.dumps({'sucesso':True,'registros':len(registros),'bytes':len(corpo),'sha256':hashlib.sha256(corpo).hexdigest()},ensure_ascii=False))
`], { env: { ...process.env, PATH: bin + path.delimiter + process.env.PATH }, encoding: 'utf8', timeout: 150000, maxBuffer: 5000000 });
  fs.rmSync(bin, { recursive: true, force: true });
  fs.writeFileSync(path.join(pasta, 'coletor.txt'), (resultado.stdout || '') + (resultado.stderr || '') + (resultado.error ? String(resultado.error) : ''));
  console.log(resultado.stdout || 'O coletor nao concluiu; consultar o artefato dnit-ao-vivo.');
  process.exitCode = resultado.status === 0 ? 0 : 1;
})().catch(e => { console.error(e); process.exitCode = 1; });
