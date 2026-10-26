const {test,expect}=require('./fixtures.cjs');

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
  const leitores=await (await page.request.get('api.pse?rota=/api/v1/status/coletores')).json();
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
    await page.goto('status.html');
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
  expect(await raiz.evaluate(n=>n.open)).toBe(false);
  await raiz.locator(':scope > summary').click();
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
  await page.goto('status.html');
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
