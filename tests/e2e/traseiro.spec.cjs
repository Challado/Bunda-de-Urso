const {test,expect}=require('./fixtures.cjs');
const {randomUUID}=require('node:crypto');
test.use({comGestao:true,comTraseiro:true,processarFila:false});
const rota=p=>'api.pse?rota='+encodeURIComponent(p);

test('rede mesh separa pendentes, valida posicao e ensina fonte sem ativa-la automaticamente',async({page,request,credenciaisGestao},info)=>{
  const origem=randomUUID();
  const instancia={uuid:origem,nome:'Instância de teste',api_url:'https://remoto.example.org/api.pse',protocolo:{nome:'intercambio-instancias',versao:1},aplicacao:'Outro sistema de radares',capacidades:{tipos_evento:['radar.v1','fonte-coleta.v1']},
    configuracao:{intervalo_segundos:300,lote:100,max_bytes:2097152,parada_programada:false,parar_em_segundos:0,retornar_em_segundos:0,anuncio_id:null}};
  const envio=await request.post(rota('/api/v1/intercambio/trocar'),{headers:{'X-Interchange-Info':Buffer.from(JSON.stringify(instancia)).toString('base64')},data:{depois:0,eventos:[{
    uuid:randomUUID(),origem,tipo:'radar.v1',chave:'teste-1',revisao:1,acao:'publicar',documento:{latitude:-23.551,longitude:-46.63,uf:'SP',via:'Rua Teste',velocidade_geral:40}
  }]}});
  expect(envio.status()).toBe(200);
  await page.goto('gestao.html');
  await page.locator('#formLogin [name=login]').fill(credenciaisGestao.login);
  await page.locator('#formLogin [name=senha]').fill(credenciaisGestao.senha);
  await page.locator('#btLogin').click();
  await page.locator('[data-aba=traseiro]').click();
  await expect(page.locator('#trResumo')).toContainText('1 posições pendentes');
  await expect(page.locator('#trInstancias')).toContainText('Instância de teste');
  const cadastro=page.locator('#trCadastros details').first();
  await cadastro.locator('summary').click();
  await expect(cadastro).toContainText('-23.551');
  await cadastro.locator('[name=motivo]').fill('Conferido no documento publico e na posicao do mapa');
  await cadastro.getByRole('button',{name:'Validar e publicar',exact:true}).click();
  await expect(page.locator('#trCadastros')).toContainText('aprovado');
  const lista=await (await page.request.get(rota('/api/v1/gestao/traseiro/cadastros'))).json();
  const id=lista.resultado.itens[0].ponto_id;
  const ponto=await (await request.get(rota('/api/v1/radares/P-'+id))).json();
  expect(ponto.resultado.pontos[0].procedencia).toBe('oficial');
  expect(ponto.resultado.pontos[0].fontes.some(f=>f.nome.startsWith('TRASEIRO DE URSO'))).toBe(true);
  await page.locator('#aba-traseiro > details').last().locator(':scope > summary').click();
  await page.locator('#trEnsinar [name=chave]').fill('fonte-de-teste');
  await page.locator('#trEnsinar [name=receita]').fill(JSON.stringify({nome:'Lista pública CSV',url:'https://fontes.example.org/lista.csv',formato:'csv',campos:{latitude:'lat',longitude:'lon',velocidade_geral:'vel'}}));
  await page.getByRole('button',{name:'Compartilhar fonte desativada'}).click();
  await expect(page.locator('#trMensagem')).toContainText('permanece desativada');
  const fonte=page.locator('#trFontes details').first();
  await fonte.locator('summary').click();
  await expect(fonte).toContainText('Leitura local: desativada');
  await fonte.getByRole('button',{name:'Ativar leitura nesta instância'}).click();
  await expect(page.locator('#trFontes')).toContainText('Leitura local: ativada');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:info.outputPath('traseiro.png'),fullPage:true,scale:'css'});
});
