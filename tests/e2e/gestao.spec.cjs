const {test,expect}=require('./fixtures.cjs');
test.use({comGestao:true,processarFila:false});
const rota=(caminho)=>'api.pse?rota='+encodeURIComponent(caminho)+'&formato=json';
const caminho=(url)=>new URL(url).searchParams.get('rota');

async function preparar(page,request,credenciais,local={latitude:-23.55,longitude:-46.63,velocidade_geral:40}){
  const envio=await request.post(rota('/api/v1/radares/submeter'),{data:local});
  expect(envio.status()).toBe(201);
  const id=(await envio.json()).resultado.cadastros[0].id;
  await page.goto('gestao.html');
  await page.locator('#formLogin [name=login]').fill(credenciais.login);
  await page.locator('#formLogin [name=senha]').fill(credenciais.senha);
  await page.locator('#btLogin').click();
  await expect(page.locator('#listaPendentes')).toContainText(id);
  await page.locator('[data-abrir="'+id+'"]').click();
  await expect(page.locator('#btRemover')).toBeVisible();
  return id;
}

test('remover limpa a tela e a fila e impede a página pública de continuar exibindo o radar',async({page,request,context,baseURL,credenciaisGestao})=>{
  const id=await preparar(page,request,credenciaisGestao);
  // A busca aceita também o número sem prefixo; excluir deve limpar a mesma tela.
  await page.locator('#buscaId').fill(id.slice(2));
  await page.locator('#btAbrirRadar').click();
  await expect(page.locator('#btRemover')).toBeVisible();
  const publico=await context.newPage();
  await publico.route('https://unpkg.com/**',r=>r.abort());
  await publico.goto(baseURL+'detalhe.html?id='+id);
  await expect(publico.locator('#principal .resumo')).toContainText(id);
  await page.bringToFront();
  await page.locator('#btRemover').click();
  await page.locator('#mMotivo').fill('Radar inexistente');
  await page.locator('#modalOk').click();
  await expect(page.locator('#avisoGer')).toContainText('removido');
  await expect(page.locator('#aba-pendentes')).toBeVisible();
  await expect(page.locator('#listaPendentes')).not.toContainText(id);
  await expect(page.locator('#radarConteudo')).toContainText('Escolha outro cadastro');
  await expect(page.locator('#btRemover')).toHaveCount(0);
  await expect(page.locator('#buscaId')).toHaveValue('');
  await page.locator('[data-aba=radar]').click();
  await expect(page.locator('#radarConteudo')).toContainText('Radar removido');
  await page.locator('[data-aba=pendentes]').click();
  await expect(page.locator('#listaPendentes')).not.toContainText(id);
  const pendentes=await page.request.get(rota('/api/v1/gestao/pendentes'));
  expect((await pendentes.json()).pendentes.map(p=>p.id)).not.toContain(id);
  expect((await request.get(rota('/api/v1/radares/'+id))).status()).toBe(404);
  await publico.bringToFront();
  // Simula o retorno a uma aba aberta antes da remoção.
  await publico.evaluate(()=>dispatchEvent(new Event('focus')));
  await expect(publico.locator('#principal .err')).toContainText('não encontrado');
  await expect(publico.locator('#metrologia')).toHaveCount(0);
  // O histórico fica disponível ao moderador, sem formulário ou ações de radar ativo.
  await page.bringToFront();
  await page.locator('[data-aba=radar]').click();
  await page.locator('#buscaId').fill(id);
  await page.locator('#btAbrirRadar').click();
  await expect(page.locator('#radarConteudo')).toContainText('apenas para consulta do histórico');
  await expect(page.locator('#histRadar')).toContainText('Radar inexistente');
  await expect(page.locator('#btRemover,#btVerificar,#btSalvar')).toHaveCount(0);
  await publico.close();
});

test('radar já verificado pode ser recruzado e substituído pelo cadastro oficial mantendo histórico',async({page,request,credenciaisGestao})=>{
  const id=await preparar(page,request,credenciaisGestao,{latitude:-24.9557,longitude:-53.4553,velocidade_geral:80});
  await page.locator('#btVerificar').click();
  await page.locator('#modalOk').click();
  await expect(page.locator('#radarConteudo .pill.ok')).toHaveText('verificado');
  for(let i=0;i<2;i++){
    await page.locator('#btCruzarRadar').click();
    await expect(page.locator('#resultadoCruzarRadar')).toContainText('1 correspondência(s)');
    await expect(page.locator('#btCruzarRadar')).toBeEnabled();
  }
  const consulta=await page.request.get(rota('/api/v1/gestao/radar/'+id));
  const radar=(await consulta.json()).radar;
  expect(radar.correspondencias).toHaveLength(1);
  expect(radar.governanca.verificacao_status).toBe('verificado');
  const oficial=radar.correspondencias[0].oficial.id;
  await expect(page.locator('#radarConteudo')).toContainText('ANTT');
  await page.getByRole('button',{name:'Usar cadastro oficial',exact:true}).click();
  await expect(page.locator('#modalCorpo')).toContainText('seu histórico é preservado');
  await page.locator('#modalOk').click();
  await expect(page.locator('#avisoGer')).toContainText('Cadastro oficial selecionado');
  await expect(page.locator('#buscaId')).toHaveValue(oficial);
  expect((await request.get(rota('/api/v1/radares/'+id))).status()).toBe(404);
  expect((await request.get(rota('/api/v1/radares/'+oficial))).status()).toBe(200);
  const historico=await page.request.get(rota('/api/v1/gestao/radar/'+id+'/historico'));
  expect((await historico.json()).historico.some(h=>h.campos?.cruzamento_oficial)).toBe(true);
});

test('menu Cruzamentos inclui verificados e não verificados e abre resultados para revisão',async({page,request,credenciaisGestao})=>{
  const id=await preparar(page,request,credenciaisGestao,{latitude:-24.9557,longitude:-53.4553,velocidade_geral:80});
  expect((await page.request.post(rota('/api/v1/gestao/radar/'+id+'/verificar'),{data:{}})).status()).toBe(200);
  expect((await request.post(rota('/api/v1/radares/submeter'),{data:{latitude:-23,longitude:-46,velocidade_geral:40}})).status()).toBe(201);
  await page.getByRole('button',{name:'Cruzamentos',exact:true}).click();
  await page.locator('#btCruzarTodos').click();
  await expect(page.locator('#progressoCruzamento')).toContainText('Concluído. 2 cadastro(s)');
  await expect(page.locator('#btCruzarTodos')).toBeEnabled();
  await expect(page.locator('#progressoCruzamento')).toContainText('1 com correspondências');
  await page.getByRole('button',{name:'Revisar '+id,exact:true}).click();
  await expect(page.locator('#aba-radar')).toBeVisible();
  await expect(page.locator('#buscaId')).toHaveValue(id);
  await expect(page.locator('#radarConteudo .pill.ok')).toHaveText('verificado');
});

test('falhas de cruzamento liberam os botões para tentar novamente e preservam o radar',async({page,request,credenciaisGestao})=>{
  const id=await preparar(page,request,credenciaisGestao);
  await page.route('**/api.pse?**',r=>{
    const c=caminho(r.request().url());
    if(c==='/api/v1/gestao/cruzamentos' || c==='/api/v1/gestao/radar/'+id+'/cruzar')
      return r.fulfill({status:503,json:{sucesso:false,erro:{mensagem:'Banco ocupado'}}});
    return r.continue();
  });
  await page.locator('#btCruzarRadar').click();
  await expect(page.locator('#resultadoCruzarRadar')).toContainText('Banco ocupado');
  await expect(page.locator('#btCruzarRadar')).toBeEnabled();
  await expect(page.locator('#buscaId')).toHaveValue(id);
  await page.getByRole('button',{name:'Cruzamentos',exact:true}).click();
  await page.locator('#btCruzarTodos').click();
  await expect(page.locator('#progressoCruzamento')).toContainText('Interrompido: Banco ocupado');
  await expect(page.locator('#btCruzarTodos')).toBeEnabled();
  await expect(page.locator('#btPararCruzamento')).toBeHidden();
  expect((await request.get(rota('/api/v1/radares/'+id))).status()).toBe(200);
});

test('Pendentes consulta novamente e ignora resposta antiga recebida depois da remoção',async({page,request,credenciaisGestao})=>{
  const id=await preparar(page,request,credenciaisGestao);
  let liberar,avisar;
  const liberarResposta=new Promise(r=>liberar=r), capturada=new Promise(r=>avisar=r);
  let primeira=true;
  await page.route('**/api.pse?**',async r=>{
    if(caminho(r.request().url())!=='/api/v1/gestao/pendentes' || !primeira) return r.continue();
    primeira=false;
    const antiga=await r.fetch();
    avisar();
    await liberarResposta;
    await r.fulfill({response:antiga});
  });
  await page.locator('[data-aba=pendentes]').click();
  await capturada;
  await page.locator('[data-aba=radar]').click();
  await page.locator('#btRemover').click();
  await page.locator('#mMotivo').fill('Duplicado');
  await page.locator('#modalOk').click();
  await expect(page.locator('#listaPendentes')).toContainText('Nenhum cadastro');
  const recebida=page.waitForResponse(r=>caminho(r.url())==='/api/v1/gestao/pendentes');
  liberar();
  await (await recebida).finished();
  await page.evaluate(()=>new Promise(requestAnimationFrame));
  await expect(page.locator('#listaPendentes')).not.toContainText(id);
  // Atualização em outra sessão também deve aparecer ao voltar à aba.
  const novo=await request.post(rota('/api/v1/radares/submeter'),{data:{latitude:-23.6,longitude:-46.7,velocidade_geral:50}});
  const outro=(await novo.json()).resultado.cadastros[0].id;
  await page.locator('[data-aba=radar]').click();
  await page.locator('[data-aba=pendentes]').click();
  await expect(page.locator('#listaPendentes')).toContainText(outro);
  await expect(page.locator('#listaPendentes')).not.toContainText(id);
});


test('falha da API ao remover mantém cadastro aberto e mostra o erro',async({page,request,credenciaisGestao})=>{
  const id=await preparar(page,request,credenciaisGestao);
  await page.route('**/api.pse?**',r=>{
    if(caminho(r.request().url())==='/api/v1/gestao/radar/'+id+'/remover')
      return r.fulfill({status:500,json:{sucesso:false,erro:{mensagem:'Não foi possível excluir.'}}});
    return r.continue();
  });
  await page.locator('#btRemover').click();
  await page.locator('#mMotivo').fill('Radar inexistente');
  await page.locator('#modalOk').click();
  await expect(page.locator('#avisoGer')).toContainText('Não foi possível excluir');
  await expect(page.locator('#aba-radar')).toBeVisible();
  await expect(page.locator('#btRemover')).toBeEnabled();
  await expect(page.locator('#radarConteudo')).toContainText(id);
  await page.locator('[data-aba=pendentes]').click();
  await expect(page.locator('#listaPendentes')).toContainText(id);
  expect((await request.get(rota('/api/v1/radares/'+id))).status()).toBe(200);
});
