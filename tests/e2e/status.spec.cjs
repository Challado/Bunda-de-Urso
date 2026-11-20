const {test,expect}=require('./fixtures.cjs');
const {validarCaixasStatus}=require('./caixas-status.cjs');

test.use({comGestao:true});
test.beforeEach(async({page,credenciaisGestao})=>{
  const r=await page.request.post('api.pse?rota=/api/v1/login',{data:credenciaisGestao});
  expect(r.status()).toBe(200);
});

test('status público carrega leituras e URLs sem entrar na gestão',async({page})=>{
  await page.context().clearCookies();
  await page.goto('status.html');
  await expect(page.locator('#estados tr')).toHaveCount(27);
  await expect(page.locator('#resumo-leitores')).toContainText('leitores exibidos');
  await page.locator('#filtro-leitores').fill('Mogi das Cruzes');
  const fonte=page.locator('#coletores .leitor:visible');
  await expect(fonte).toHaveCount(1);
  await fonte.locator('summary').click();
  await expect(fonte.getByRole('link').first()).toHaveAttribute('href',/^https:\/\/dados\.mogidascruzes\.sp\.gov\.br\//);
  await expect(page.locator('#acesso-diagnostico')).toBeHidden();
});

test('diagnóstico sem sessão mantém o status público',async({page})=>{
  await page.context().clearCookies();
  await page.goto('status.html?diagnostico=1');
  await expect(page.locator('#acesso-diagnostico').getByRole('link')).toHaveAttribute('href',/gestao\.html$/);
  await expect(page.locator('#resumo-leitores')).toContainText('leitores exibidos');
  await expect(page.locator('#erro-leitores')).toBeHidden();
});

test('status: 27 UFs, detalhes em nova aba, leitores e recolhimento',async({page})=>{
  await page.goto('status.html');
  await expect(page.locator('#estados tr')).toHaveCount(27);
  await expect(page.locator('#estados tr').first()).toContainText('Acre');
  await expect(page.locator('#estados tr').last()).toContainText('Tocantins');
  await expect(page.locator('#estados tr').last().locator('td').first()).toHaveText('27');
  const pr=page.getByRole('link',{name:'Paraná (PR)'});
  await expect(pr).toHaveAttribute('target','_blank');
  const [aba]=await Promise.all([page.waitForEvent('popup'),pr.click()]);
  await expect(aba.locator('#nome-estado')).toHaveText('Paraná (PR)');
  await expect(aba.locator('#pontos tr')).toHaveCount(1);
  await expect(aba.locator('#totais')).toContainText('Federais');
  await expect(aba.locator('#pontos')).toContainText('Federal');
  await expect(aba.locator('#fontes')).toContainText('ANTT');
  await expect(aba.locator('#progresso')).toContainText('1 de 1');
  await aba.close();
  const leitores=await (await page.request.get('api.pse?rota=/api/v1/status/leituras')).json();
  expect(leitores.resultado.total).toBeGreaterThan(1);
  await expect(page.locator('#coletores .leitor')).toHaveCount(leitores.resultado.total);
  await expect(page.locator('#erro-leitores')).toBeHidden();
  await page.locator('#filtro-leitores').fill('ANTT');
  const leitor=page.locator('#coletores .leitor:visible');
  await expect(leitor).toHaveCount(1);
  await leitor.locator('summary').click();
  await expect(leitor).toContainText('Última leitura bem-sucedida');
  await expect(leitor).toContainText('Leitura OK');
  await expect(leitor.locator('a').first()).toHaveAttribute('href',/gov.br/);
  await page.locator('#leituras>summary').click();
  await expect(page.locator('#filtro-leitores')).toBeHidden();
  await page.locator('#leituras>summary').click();
  await expect(page.locator('#filtro-leitores')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await page.screenshot({path:test.info().outputPath('status.png'),fullPage:true});
});

test('status: falha de API informa erro e permite tentar novamente',async({page})=>{
  await page.route('**/api.pse?**',route=>{
    const url=new URL(route.request().url());
    if(url.searchParams.get('rota')==='/api/v1/status/estados')return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({sucesso:false,erro:{mensagem:'Banco indisponível'}})});
    return route.continue();
  });
  await page.goto('status.html');
  await expect(page.locator('#erro-cobertura')).toContainText('Banco indisponível');
  await expect(page.locator('#atualizar')).toBeEnabled();
  await page.unroute('**/api.pse?**');
  await page.locator('#atualizar').click();
  await expect(page.locator('#estados tr')).toHaveCount(27);
  await expect(page.locator('#erro-cobertura')).toBeHidden();
});

test('estado: UF sem cadastros e UF inválida',async({page})=>{
  await page.goto('status-estado.html?uf=AC');
  await expect(page.locator('#nome-estado')).toHaveText('Acre (AC)');
  await expect(page.locator('#progresso')).toContainText('0 de 0');
  await expect(page.locator('#mais')).toBeHidden();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await page.goto('status-estado.html?uf=XX');
  await expect(page.locator('#erro-cobertura')).toContainText('27 siglas');
});

test.describe('fontes documentais',()=>{
  test.use({comDocumentacao:true});
  test('documentos lidos mantêm cadastro pendente e erros continuam vermelhos',async({page})=>{
    await page.goto('status.html?diagnostico=1');
    await page.locator('#filtro-leitores').fill('STTU Natal');
    const leitor=page.locator('#coletores .leitor:visible');
    await expect(leitor).toHaveCount(1);
    await expect(leitor.locator('summary')).toContainText('Documentação lida');
    await expect(leitor.locator('summary')).toContainText('Cadastro de radares pendente');
    await expect(leitor.locator('summary .selo.ok')).toHaveCount(0);
    await leitor.locator('summary').click();
    await expect(leitor).toContainText('Registros de documentação aceitos');
    const doc=await (await page.request.get('api.pse?rota=/api/v1/status/coletores')).json();
    const natal=doc.resultado.coletores.find(c=>c.conector==='natal_rn');
    natal.estado='erro';natal.ultima_tentativa.erro_detalhe='Página de origem não reconhecida';
    await page.route('**/api.pse?**',route=>new URL(route.request().url()).searchParams.get('rota')==='/api/v1/status/coletores'
      ?route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(doc)}):route.continue());
    await page.locator('#atualizar').click();
    await expect(leitor.locator('summary .selo.falha')).toHaveText('Erro na leitura');
    await leitor.locator('summary').click();
    await expect(leitor).toContainText('Página de origem não reconhecida');
  });
});


test('fontes ficam na arvore Federal, estado e municipio com busca e aberturas preservadas',async({page})=>{
  await page.goto('status.html');
  await expect(page.locator('.estado-leitores')).toHaveCount(27);
  const raiz=page.locator('.territorio-federal');
  await expect(raiz).toHaveAttribute('open','');
  await expect(page.locator('.estado-leitores:visible')).toHaveCount(27);
  await expect(page.locator('.estado-leitores[open]')).toHaveCount(0);
  const cabecalho=raiz.locator(':scope > summary');
  await cabecalho.focus();
  await cabecalho.press('Enter');
  await expect(page.locator('.estado-leitores:visible')).toHaveCount(0);
  await cabecalho.press('Enter');
  await expect(raiz.locator(':scope > .filhos-leitores > .fonte-leitores').filter({hasText:'ANTT'})).toHaveCount(1);
  const ce=page.locator('.estado-leitores[data-uf="CE"]');
  await ce.locator(':scope > summary').click();
  const fortaleza=ce.locator('.municipio-leitores[data-municipio="2304400"]');
  await fortaleza.locator(':scope > summary').click();
  const amc=fortaleza.locator('.fonte-leitores').filter({has:page.locator(':scope > summary',{hasText:'AMC Fortaleza'})});
  await expect(amc).toHaveCount(1);
  await expect(ce.locator(':scope > .filhos-leitores > .vazio-grupo').first()).toContainText('Nenhuma fonte estadual');
  await page.locator('#atualizar').click();
  await expect(ce).toHaveAttribute('open','');
  await expect(fortaleza).toHaveAttribute('open','');
  await page.locator('#filtro-leitores').fill('fortaleza');
  await expect(page.locator('.estado-leitores:visible')).toHaveCount(1);
  await expect(page.locator('.leitor:visible')).toHaveCount(1);
  await validarCaixasStatus(page);
  await page.screenshot({path:test.info().outputPath('caixas-aninhadas.png'),fullPage:true});
  await ce.locator(':scope > summary').click();
  await expect(fortaleza).toBeHidden();
  await ce.locator(':scope > summary').click();
  await expect(fortaleza).toBeVisible();
  await expect(fortaleza).toHaveAttribute('open','');
  await expect(page.locator('#resumo-leitores')).toContainText('1 de ');
  await page.locator('#filtro-leitores').fill('Sao Paulo');
  await expect(page.locator('.estado-leitores:visible')).toHaveCount(1);
  await expect(page.locator('.estado-leitores:visible')).toHaveAttribute('data-uf','SP');
  await page.locator('#filtro-leitores').fill('sem resultado zzz');
  await expect(page.locator('#sem-leitores')).toBeVisible();
  await page.locator('#filtro-leitores').clear();
  await expect(ce).toHaveAttribute('open','');
  await expect(fortaleza).toHaveAttribute('open','');
  await page.locator('#recolher-leitores').click();
  await expect(raiz).not.toHaveAttribute('open');
  await page.locator('#expandir-leitores').click();
  await expect(page.locator('#coletores .leitor:not([open])')).toHaveCount(0);
  await expect(page.locator('#coletores')).toContainText('Última tentativa');
});

test('fontes sem local ficam visiveis e multiplas localidades nao duplicam o total',async({page})=>{
  const d=(await (await page.request.get('api.pse?rota=/api/v1/status/coletores')).json()).resultado;
  const leitor={...d.coletores[0],id:99991,fonte_id:99991,fonte:'Consórcio municipal de teste',esfera:'municipal',localidades:[
    {uf:'GO',nome_uf:'Goiás',municipio_ibge:'5208707',municipio:'Goiânia'},
    {uf:'PR',nome_uf:'Paraná',municipio_ibge:'4104808',municipio:'Cascavel'}]};
  const semLocal={...leitor,id:99992,fonte_id:99992,fonte:'Fonte sem município confirmado',localidades:[]};
  d.coletores=[leitor,semLocal];d.total=2;
  await page.route('**/api.pse?**',r=>new URL(r.request().url()).searchParams.get('rota')==='/api/v1/status/coletores'?r.fulfill({json:{sucesso:true,resultado:d}}):r.continue());
  await page.goto('status.html?diagnostico=1');
  await expect(page.locator('.leitor')).toHaveCount(3);
  await expect(page.locator('#resumo-leitores')).toHaveText('2 de 2 leitores exibidos.');
  await page.locator('#expandir-leitores').click();
  await expect(page.locator('.estado-leitores[data-uf="GO"] .fonte-leitores')).toContainText('Consórcio');
  await expect(page.locator('.estado-leitores[data-uf="PR"] .fonte-leitores')).toContainText('Consórcio');
  await expect(page.locator('.sem-local-leitores')).toContainText('Fonte sem município confirmado');
  await page.locator('#filtro-leitores').fill('consorcio');
  await expect(page.locator('.leitor:visible')).toHaveCount(2);
  await expect(page.locator('#resumo-leitores')).toHaveText('1 de 2 leitores exibidos.');
});

test('contadores de erro filtram a arvore e permitem restaurar a exibicao',async({page})=>{
  const resposta=await (await page.request.get('api.pse?rota=/api/v1/status/coletores')).json();
  const {coletores}=resposta.resultado;
  const antt=coletores.find(r=>r.conector==='antt');
  const fortaleza=coletores.find(r=>r.conector==='amc_ce');
  antt.estado='erro';
  fortaleza.estado='interrompido';
  coletores.push({...fortaleza,id:99993,fonte_id:99993,ativo:false,fonte:'Leitor inativo'});
  resposta.resultado.total=coletores.length;
  await page.route('**/api.pse?**',r=>new URL(r.request().url()).searchParams.get('rota')==='/api/v1/status/coletores'
    ?r.fulfill({json:resposta}):r.continue());
  await page.goto('status.html?diagnostico=1');

  const brasil=page.locator('.territorio-federal');
  const ce=page.locator('.estado-leitores[data-uf="CE"]');
  const contador=brasil.locator(':scope > summary').getByRole('button',{name:'2 com erro'});
  const filtro=page.getByRole('button',{name:'Só com erro'});
  const leitores=page.locator('.leitor:visible');
  const resumo=page.locator('#resumo-leitores');

  await contador.focus();
  await contador.press('Enter');
  await expect(contador).toHaveAttribute('aria-pressed','true');
  await expect(contador).toBeFocused();
  await expect(brasil).toHaveAttribute('open','');
  await expect(leitores).toHaveCount(2);
  await expect(leitores.locator('summary')).toHaveText([/Erro na leitura/,/Leitura interrompida/]);
  await expect(resumo).toHaveText(`2 de ${coletores.length} leitores exibidos.`);
  await filtro.click();
  await expect(filtro).toHaveAttribute('aria-pressed','false');
  await expect(ce).not.toHaveAttribute('open');
  await expect(resumo).toHaveText(`${coletores.length} de ${coletores.length} leitores exibidos.`);

  const errosCe=ce.locator(':scope > summary').getByRole('button',{name:'1 com erro'});
  await errosCe.click();
  await expect(errosCe).toHaveAttribute('aria-pressed','true');
  await expect(leitores).toHaveCount(1);
  await expect(leitores).toContainText('Leitura interrompida');
  await errosCe.click();
  await expect(ce).not.toHaveAttribute('open');

  await page.locator('#filtro-leitores').fill('erro');
  await expect(leitores).toHaveCount(2);
  await page.locator('#filtro-leitores').clear();
  await filtro.click();
  await expect(leitores).toHaveCount(2);
  await expect(filtro).toHaveAttribute('aria-pressed','true');
});

test('todos os contadores filtram os mesmos leitores que contam',async({page})=>{
  const go={uf:'GO',nome_uf:'Goiás',municipio_ibge:'5208707',municipio:'Goiânia'};
  const ce={uf:'CE',nome_uf:'Ceará',municipio_ibge:'2304400',municipio:'Fortaleza'};
  const leitor=(id,recurso,ajustes={})=>({
    id,recurso,fonte_id:101,fonte:'Agência Municipal',localidades:[go],
    esfera:'municipal',ativo:true,agendado:true,estado:'ok',tipo_coleta:'cadastro',
    ...ajustes,
  });
  const coletores=[
    leitor(1,'Leitura normal'),
    leitor(2,'Mesmo arquivo',{estado:'sem_mudanca'}),
    leitor(3,'Falha estadual',{estado:'erro'}),
    leitor(4,'Falha nacional',{estado:'interrompido',esfera:'federal',fonte:'Governo Federal',fonte_id:102,localidades:[]}),
    leitor(5,'Edital publicado',{tipo_coleta:'documental',estado:'documentado'}),
    leitor(6,'Edital sem alteração',{tipo_coleta:'documental',estado:'sem_mudanca'}),
    leitor(7,'Leitor novo',{estado:'nunca_coletado',localidades:[go,ce]}),
    leitor(8,'Leitor em andamento',{estado:'em_andamento'}),
    leitor(9,'Leitor sem dados',{estado:'sem_dados'}),
    leitor(10,'Leitor atrasado',{leitura_atrasada:true}),
    leitor(11,'Leitor com rejeições',{ultima_tentativa:{linhas_rejeitadas:1}}),
    leitor(12,'Leitor com atenção',{atencao:true}),
    leitor(13,'Camada histórica',{estado:'erro',ativo:false}),
  ];
  const resultado={estados:[{uf:'CE',nome:'Ceará'},{uf:'GO',nome:'Goiás'}],coletores,total:coletores.length};
  await page.route('**/api.pse?**',r=>new URL(r.request().url()).searchParams.get('rota')==='/api/v1/status/leituras'
    ?r.fulfill({json:{sucesso:true,resultado}}):r.continue());
  await page.goto('status.html');

  const brasil=page.locator('.territorio-federal');
  const goias=page.locator('.estado-leitores[data-uf="GO"]');
  const busca=page.locator('#filtro-leitores');
  const limpar=page.getByRole('button',{name:'Limpar filtros'});
  const leitores=page.locator('.leitor:visible');
  const botao=(grupo,nome)=>grupo.locator(':scope > summary').getByRole('button',{name:nome,exact:true});
  const ids=()=>leitores.evaluateAll(itens=>[...new Set(itens.map(n=>Number(n.dataset.leitor.split(':')[1])))].sort((a,b)=>a-b));

  for(const [nome,esperados] of [
    ['1 desativado',[13]],['8 pendentes',[5,6,7,8,9,10,11,12]],['2 OK',[1,2]],['2 com erro',[3,4]],
  ]){
    const filtro=botao(brasil,nome);
    await filtro.focus();
    await filtro.press('Space');
    await expect(filtro).toHaveAttribute('aria-pressed','true');
    await expect.poll(ids).toEqual(esperados);
    await expect(page.locator('#resumo-leitores')).toHaveText(`${esperados.length} de 13 leitores exibidos.`);
    await filtro.click();
    await expect(filtro).toHaveAttribute('aria-pressed','false');
    await expect(goias).not.toHaveAttribute('open');
  }

  for(const [termo,esperados] of [
    ['DESATIVADOS',[13]],['pendentes',[5,6,7,8,9,10,11,12]],['ok',[1,2]],['com erros',[3,4]],
    ['GO',[1,2,3,5,6,7,8,9,10,11,12,13]],['fortaleza',[7]],['rejeicoes',[11]],['Leitura atrasada',[10]],
  ]){
    await busca.fill(termo);
    await expect.poll(ids).toEqual(esperados);
  }
  await limpar.click();
  await expect(busca).toBeFocused();
  await expect(busca).toHaveValue('');
  await goias.locator(':scope > summary > .titulo-grupo').click();
  await expect(goias).toHaveAttribute('open','');
  const municipio=goias.locator('.municipio-leitores');
  await municipio.locator(':scope > summary > .titulo-grupo').click();
  await expect(municipio).toHaveAttribute('open','');
  const pendentesMunicipio=botao(municipio,'8 pendentes');
  await pendentesMunicipio.click();
  await expect.poll(ids).toEqual([5,6,7,8,9,10,11,12]);
  await pendentesMunicipio.click();
  const fonte=municipio.locator('.fonte-leitores');
  await botao(fonte,'1 desativado').click();
  await expect.poll(ids).toEqual([13]);
  await expect(botao(fonte,'1 desativado')).toHaveAttribute('aria-pressed','true');

  await botao(brasil,'2 com erro').click();
  await expect.poll(ids).toEqual([3,4]);
  await busca.fill('AGENCIA');
  await expect(botao(brasil,'1 com erro')).toHaveAttribute('aria-pressed','true');
  await expect.poll(ids).toEqual([3]);
  await page.locator('#atualizar').click();
  await expect(botao(brasil,'1 com erro')).toHaveAttribute('aria-pressed','true');
  await expect.poll(ids).toEqual([3]);
  await busca.fill('sem correspondência');
  await expect(page.locator('#sem-leitores')).toBeVisible();
  await expect(leitores).toHaveCount(0);
  await expect(limpar).toBeVisible();
  await limpar.click();
  await expect(page.locator('#sem-leitores')).toBeHidden();
  await expect(goias).toHaveAttribute('open','');
  await expect(municipio).toHaveAttribute('open','');
  await expect(page.locator('#resumo-leitores')).toHaveText('13 de 13 leitores exibidos.');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});
