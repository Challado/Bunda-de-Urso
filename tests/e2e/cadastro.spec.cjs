const {test,expect} = require('./fixtures.cjs');
const ROTA='**/api.pse?rota=/api/v1/radares/submeter&formato=json';
const campo=(page,nome)=>page.locator('[name="'+nome+'"]');
async function preencher(page,lat='-24,9555',lon='-53,4552',vel='60'){
  await campo(page,'latitude').fill(lat);
  await campo(page,'longitude').fill(lon);
  await campo(page,'velocidade_geral').fill(vel);
}
async function envio(request,protocolo){
  const r=await request.get('api.pse?rota=/api/v1/radares/envios/'+protocolo);
  expect(r.status()).toBe(200);return (await r.json()).resultado;
}
async function enviar(page){
  const [r]=await Promise.all([
    page.waitForResponse(r=>r.url().includes('rota=/api/v1/radares/submeter') && r.request().method()==='POST'),
    page.getByRole('button',{name:'Enviar cadastro',exact:true}).click(),
  ]);
  expect(r.status()).toBe(202);
  expect(r.request().headers().prefer).toBe('respond-async');
  const recebido=await r.json();expect(recebido.sucesso).toBe(true);
  await expect(page.locator('#bt')).toBeEnabled();
  const protocolo=recebido.resultado.protocolo;
  await expect.poll(async()=> (await envio(page.request,protocolo)).estado).toBe('processado');
  const final=await envio(page.request,protocolo);
  const consultar=page.locator('#btConsultarEnvio');
  if(await consultar.count())await consultar.click();
  await expect(page.locator('#res')).toContainText(/Cadastro recebido|nenhuma duplicata/);
  return {doc:{sucesso:true,resultado:final.resultado},payload:r.request().postDataJSON(),recibo:recebido.resultado};
}
async function detalhe(request,id){
  const r=await request.get('api.pse?rota=/api/v1/radares/'+id+'&formato=json');
  expect(r.ok()).toBe(true);return (await r.json()).resultado.pontos[0];
}

test('simplificado envia três campos, salva e consulta sem alterar o oficial',async({page,request})=>{
  await page.goto('cadastro.html');
  await expect(page.locator('#camposExpert')).toBeHidden();
  await expect(page.locator('input:visible:not([type=radio])')).toHaveCount(3);
  await preencher(page);
  const {doc,payload}=await enviar(page);
  expect(payload).toEqual({latitude:-24.9555,longitude:-53.4552,velocidade_geral:60});
  await expect(page.locator('#res')).toContainText('Cadastro recebido');
  const cadastro=doc.resultado.cadastros[0], ponto=await detalhe(request,cadastro.id);
  expect(ponto.localizacao.latitude).toBe(-24.9555);
  expect(ponto.velocidade_geral_kmh).toBe(60);
  expect(ponto.verificacao_status).toBe('nao_verificado');
  expect(cadastro.proximidade.campos_complementados.via).toBe('BR-277');
  const oficial=await detalhe(request,'P-1');
  expect(oficial.velocidade_leves_kmh).toBe(80);
  expect(oficial.localizacao.latitude).toBe(-24.9556);
  const repetido=await enviar(page);
  expect(repetido.recibo.reenvio).toBe(true);
  expect(repetido.doc.resultado.cadastros[0].id).toBe(cadastro.id);
  await expect(page.locator('#res')).toContainText('nenhuma duplicata');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('expert aceita município e via; campos ocultos não vazam no simplificado',async({page})=>{
  await page.goto('cadastro.html');
  await page.getByRole('radio',{name:'Expert',exact:true}).check();
  await campo(page,'municipio').fill('Cascavel');await campo(page,'uf').fill('PR');
  await campo(page,'via').fill('BR-999');await campo(page,'km').fill('10,5');
  const expert=await enviar(page);
  expect(expert.payload).toEqual({municipio:'Cascavel',uf:'PR',via:'BR-999',km:10.5});
  expect(expert.doc.resultado.cadastros[0].proximidade.status).toBe('sem_coordenadas');
  await page.getByRole('radio',{name:'Simplificado',exact:true}).check();
  await preencher(page,'-23.55','-46.63','40');
  const simples=await enviar(page);
  expect(simples.payload).toEqual({latitude:-23.55,longitude:-46.63,velocidade_geral:40});
});

test('validação local impede envios incompletos ou inválidos',async({page})=>{
  let pedidos=0;page.on('request',r=>{if(r.method()==='POST')pedidos++;});
  await page.goto('cadastro.html');await page.locator('#bt').click();
  await expect(page.locator('#res')).toContainText('Informe latitude, longitude e velocidade');
  await preencher(page,'abc','-53','60');await page.locator('#bt').click();
  await expect(page.locator('#res')).toContainText('latitude e longitude válidas');
  await preencher(page,'-24','-53','0');await page.locator('#bt').click();
  await expect(page.locator('#res')).toContainText('velocidade maior que zero');
  expect(pedidos).toBe(0);await expect(page.locator('#bt')).toBeEnabled();
});

test('GPS negado mantém o envio manual disponível',async({page})=>{
  await page.addInitScript(()=>Object.defineProperty(navigator,'geolocation',{value:{
    getCurrentPosition:(_ok,erro)=>erro({code:1}),
  }}));
  await page.goto('cadastro.html');await page.locator('#btGeo').click();
  await expect(page.locator('#geoInfo')).toContainText('negada');
  await preencher(page);await enviar(page);
  await expect(page.locator('#res')).toContainText('Cadastro recebido');
});

test('falha de rede libera o botão, preserva os campos e permite tentar de novo',async({page,context})=>{
  await page.goto('cadastro.html');await preencher(page);
  await context.setOffline(true);await page.locator('#bt').click();
  await expect(page.locator('#res')).toContainText('Não foi possível confirmar');
  await expect(page.locator('#bt')).toBeEnabled();
  await expect(campo(page,'latitude')).toHaveValue('-24,9555');
  await context.setOffline(false);await enviar(page);
  await expect(page.locator('#res')).toContainText('Cadastro recebido');
});

test('erro HTTP não prende o formulário nem anuncia sucesso',async({page})=>{
  await page.route(ROTA,route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({sucesso:false,erro:{mensagem:'Serviço temporariamente indisponível'}})}));
  await page.goto('cadastro.html');await preencher(page);await page.locator('#bt').click();
  await expect(page.locator('#res')).toContainText('HTTP 503');
  await expect(page.locator('#res')).not.toContainText('Cadastro recebido');
  await expect(page.locator('#bt')).toBeEnabled();
  await expect(campo(page,'velocidade_geral')).toHaveValue('60');
});

for(const temAbort of [true,false]){
  test('resposta perdida após gravar: prazo, reenvio e resposta atrasada'+(temAbort?'':' sem AbortController'),async({page,request})=>{
    if(!temAbort)await page.addInitScript(()=>{window.AbortController=undefined;});
    await page.clock.install();
    let rotaPresa,respostaPresa;
    let confirmar;
    const gravado=new Promise(resolve=>{confirmar=resolve;});
    await page.route(ROTA,async route=>{
      if(!rotaPresa){
        rotaPresa=route;
        // A API verdadeira grava. Somente a entrega da resposta e interrompida.
        respostaPresa=await route.fetch();confirmar(await respostaPresa.json());
        return;
      }
      await route.continue();
    });
    await page.goto('cadastro.html');await preencher(page);await page.locator('#bt').click();
    const primeiro=await gravado;
    expect(primeiro.resultado.protocolo).toMatch(/^[a-f0-9]{32}$/);
    await expect(page.locator('#bt')).toHaveText('Enviando…');
    // O cenario e a resposta perdida de um cadastro ja processado. A entrega
    // segue presa no navegador; aguardamos o worker real antes do reenvio.
    await expect.poll(async()=> (await envio(request,primeiro.resultado.protocolo)).estado).toBe('processado');
    await page.clock.fastForward(20001);
    await expect(page.locator('#res')).toContainText('não confirmou o envio em 20 segundos');
    await expect(page.locator('#bt')).toBeEnabled();
    await expect(campo(page,'latitude')).toHaveValue('-24,9555');
    const repetido=await enviar(page);
    expect(repetido.recibo.reenvio).toBe(true);
    expect(repetido.recibo.protocolo).toBe(primeiro.resultado.protocolo);
    await expect(page.locator('#res')).toContainText('nenhuma duplicata');
    // Com abort, o navegador pode ja ter cancelado a primeira resposta.
    if(temAbort)await rotaPresa.fulfill({response:respostaPresa}).catch(()=>{});
    else await rotaPresa.fulfill({response:respostaPresa});
    await page.waitForTimeout(100);
    await expect(page.locator('#res')).toContainText('nenhuma duplicata');
    const final=await envio(request,primeiro.resultado.protocolo);
    expect((await detalhe(request,final.resultado.cadastros[0].id)).velocidade_geral_kmh).toBe(60);
  });
}


test.describe('fila sem processamento imediato',()=>{
  test.use({processarFila:false});
  test('ACK mostra protocolo sem anunciar radar pronto e retoma pelo link',async({page,request})=>{
    await page.goto('cadastro.html');await preencher(page);
    const [r]=await Promise.all([
      page.waitForResponse(r=>r.url().includes('radares/submeter')&&r.request().method()==='POST'),
      page.locator('#bt').click(),
    ]);
    expect(r.status()).toBe(202);
    const protocolo=(await r.json()).resultado.protocolo;
    await expect(page.locator('#res')).toContainText('Envio recebido e salvo');
    await expect(page.locator('#res')).not.toContainText('Cadastro recebido!');
    await expect(page.locator('#res a[href*="detalhe.html"]')).toHaveCount(0);
    await expect(page.locator('#bt')).toBeEnabled();
    expect((await envio(request,protocolo)).estado).toBe('recebido');
    await page.goto('cadastro.html?envio='+protocolo);
    await expect(page.locator('#res')).toContainText(protocolo);
    await expect(page.locator('#res')).toContainText('Aguardando processamento');
    const salvo=await page.evaluate(()=>JSON.parse(localStorage.getItem('radar.envio')));
    expect(Object.keys(salvo).sort()).toEqual(['em','protocolo']);
    expect(salvo.protocolo).toBe(protocolo);
  });
  test('protocolo inexistente não é anunciado como recebido',async({page})=>{
    await page.goto('cadastro.html?envio='+'f'.repeat(32));
    await expect(page.locator('#res')).toContainText('Protocolo não encontrado');
    await expect(page.locator('#res')).not.toContainText('Envio recebido e salvo');
  });
  test('armazenamento bloqueado não impede envio nem consulta pelo link',async({page})=>{
    await page.addInitScript(()=>Object.defineProperty(window,'localStorage',{get(){throw new Error('bloqueado');}}));
    await page.goto('cadastro.html');await preencher(page);
    const [r]=await Promise.all([
      page.waitForResponse(r=>r.url().includes('radares/submeter')&&r.request().method()==='POST'),
      page.locator('#bt').click(),
    ]);
    const protocolo=(await r.json()).resultado.protocolo;
    await expect(page.locator('#res')).toContainText('Envio recebido e salvo');
    await page.goto('cadastro.html?envio='+protocolo);
    await expect(page.locator('#res')).toContainText('Aguardando processamento');
  });
});
