const {test,expect}=require('./fixtures.cjs');
const fs=require('node:fs');
const path=require('node:path');
test.use({comMetrologia:true,processarFila:false});

test('detalhe usa equipamento comum às fontes e preserva suas publicações',async({page,request})=>{
  const response=await request.get('api.pse?rota=/api/v1/radares/P-1&formato=json');
  expect(response.status()).toBe(200);
  const p=(await response.json()).resultado.pontos[0];
  expect(p.id).toBe('P-1');
  expect(p.localizacao.latitude).toBe(-24.9556);
  expect(p.velocidade_leves_kmh).toBe(80);
  const equipamento=p.equipamentos[0];
  expect(equipamento.id).toBe('E-1');
  expect(equipamento.instalacoes).toHaveLength(2);
  expect(equipamento.juncao_metrologica).toBeUndefined();
  expect(equipamento.verificacoes_metrologicas).toHaveLength(1);
  expect(equipamento.verificacoes_metrologicas[0].validade_ate).toBe('2027-06-24');
  const original=(await (await request.get('api.pse?rota=/api/v1/radares/P-2')).json()).resultado.pontos[0];
  expect(original.localizacao.latitude).toBeNull();
  expect(original.equipamentos[0].id).toBe(equipamento.id);
  expect(original.equipamentos[0].verificacoes_metrologicas).toHaveLength(1);
  await page.route('https://unpkg.com/**',r=>r.abort());
  await page.goto('detalhe.html?id=P-1');
  await expect(page.locator('#metrologia')).toContainText('Há publicação do Inmetro/PSIE');
  await expect(page.locator('#metrologia')).toContainText('24/06/2027');
  await expect(page.locator('details.fonte')).toHaveCount(2);
  const inmetro=page.locator('details.fonte').filter({has:page.locator('summary h3',{hasText:'INMETRO'})});
  await expect(inmetro).toContainText('Dados publicados para este aparelho');
  await expect(inmetro).toContainText('24/06/2027');
  expect(await inmetro.evaluate(e=>e.open)).toBe(true);
  await page.getByRole('button',{name:'Recolher fontes',exact:true}).click();
  expect(await inmetro.evaluate(e=>e.open)).toBe(false);
  await page.getByRole('button',{name:'Expandir fontes',exact:true}).click();
  expect(await inmetro.evaluate(e=>e.open)).toBe(true);
  await expect(page.locator('.mapas-principais a')).toHaveCount(3);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});


test.describe('radar sem série na ANTT',()=>{
  test.use({comMetrologia:'cadastral'});
  test('mostra correspondência cadastral do Inmetro sem confirmar identidade física',async({page,request})=>{
    const resposta=await (await request.get('api.pse?rota=/api/v1/radares/P-1')).json();
    const p=resposta.resultado.pontos[0];
    expect(p.localizacao.km).toBe(597.42);
    expect(p.equipamentos[0].numero_serie).toBeNull();
    expect(p.correspondencia_metrologica.estado).toBe('compativel');
    expect(p.correspondencia_metrologica.candidatos[0].numero_serie).toBe('FSC110-0811');
    expect(p.correspondencia_metrologica.candidatos[0].identidade_fisica_confirmada).toBe(false);
    expect(p.correspondencia_metrologica.candidatos[0].verificacoes_metrologicas[0].numero_certificado).toBe('16415173');
    // A API real fornece ANTT/Inmetro; acrescenta o contrato PRF e seus históricos
    // para exercitar a apresentação de divergências e coletas repetidas no navegador.
    const prf=JSON.parse(fs.readFileSync(path.join(__dirname,'../fixtures/novos/correspondencia_e604.json'))).prf;
    p.correspondencia_metrologica.divergencias=Array.from({length:8},()=>({campo:'situacao_operacional',valor_principal:'ativo',valor_correspondente:'inativo',valor_publicado:'INOPERANTE',fonte:'PRF - Radares fixos',registro_id:71313}));
    p.dados_por_fonte.push({nome:'PRF - Radares fixos',natureza:'oficial',registros:[
      {id_registro_original:'EPI016',dados_publicados:prf,coletado_em:'2026-10-10T17:00:00Z'},
      {id_registro_original:'EPI016',dados_publicados:prf,coletado_em:'2026-10-20T17:00:00Z'},
      {id_registro_original:'EPI016',dados_publicados:{...prf,ESTADO:'OPERANTE'},coletado_em:'2026-10-21T17:00:00Z'}]});
    await page.route('**/api.pse?**',r=>r.fulfill({json:resposta}));
    await page.route('https://unpkg.com/**',r=>r.abort());
    await page.goto('detalhe.html?id=P-1');
    await expect(page.locator('#metrologia')).toContainText('Foi encontrado um registro compatível no Inmetro');
    await expect(page.locator('#metrologia')).toContainText('FSC110-0811');
    await expect(page.locator('#metrologia')).toContainText('16415173');
    await expect(page.locator('#metrologia')).toContainText('03/05/2027');
    await expect(page.locator('#metrologia')).not.toContainText('Não foi possível relacionar');
    const fonte=page.locator('details.fonte').filter({has:page.locator('summary h3',{hasText:'INMETRO'})});
    await expect(fonte).toContainText('Registro compatível com este local');
    await expect(fonte).toContainText('16176985');
    await expect(page.locator('#metrologia')).toContainText('Após reparo');
    await expect(page.locator('#metrologia')).toContainText('ID do equipamento');
    await expect(page.locator('#metrologia')).toContainText('Ponto');
    await expect(page.locator('.alerta-fontes')).toContainText('INOPERANTE');
    await expect(page.locator('.alerta-fontes')).toContainText('PRF');
    await expect(page.locator('details.fonte')).toHaveCount(3);
    await expect(page.locator('.alerta-fontes p')).toHaveCount(2);
    const fontePrf=page.locator('details.fonte').filter({has:page.locator('summary h3',{hasText:'PRF'})});
    await expect(fontePrf.locator('.publicacao')).toHaveCount(2);
    await expect(fontePrf.locator('.publicacao').last()).toContainText('OPERANTE');
    await expect(fontePrf).toContainText('10/10/2026');
    await expect(fontePrf).toContainText('20/10/2026');
    await expect(page.locator('#principal')).not.toContainText(/municipio_rodovia_km|Estado da resolução|Registros origem|Identidade física confirmada|snapshot|Hash do artefato|Procedência da resposta|fonte_registro_id/);
    const tamanhos=page.viewportSize().width>620?[1920,1280,1024,768]:[390,320];
    for(const largura of tamanhos){
      await page.setViewportSize({width:largura,height:900});
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
      const bloco=await page.locator('#metrologia').boundingBox();
      expect(bloco.width).toBeGreaterThan(largura*0.9);
      const certificado=await page.locator('.verificacao').first().boundingBox();
      expect(certificado.width).toBeGreaterThan(Math.min(280,largura-100));
      await expect(page.locator('dl dl')).toHaveCount(0);
    }
  });
});


test('avisa sobre posição estimada e limites divergentes sem esconder valores publicados',async({page,request})=>{
  const resposta=await (await request.get('api.pse?rota=/api/v1/radares/P-1')).json();
  const p=resposta.resultado.pontos[0];
  p.localizacao.qualidade='inferida';
  p.conflitos=[{campo:'limite_velocidade',categoria:'leves',faixa_id:'F-1',valores_kmh:[60,80]}];
  await page.route('**/api.pse?**',r=>r.fulfill({json:resposta}));
  await page.route('https://unpkg.com/**',r=>r.abort());
  await page.goto('detalhe.html?id=P-1');
  await expect(page.locator('#principal')).toContainText('Localização aproximada');
  await expect(page.locator('#principal')).toContainText('60 e 80 km/h');
  await expect(page.locator('.resumo')).toContainText('Limites de velocidade divergentes');
  await expect(page.locator('details.fonte')).toHaveCount(2);
  await expect(page.locator('#principal')).not.toContainText('F-1');
});
