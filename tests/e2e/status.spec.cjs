const {test,expect}=require('./fixtures.cjs');

test('status: 27 UFs, detalhes em nova aba, leitores e recolhimento',async({page})=>{
  await page.goto('resources/status.html');
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
  await expect(page.locator('#coletores>.leitor')).toHaveCount(leitores.resultado.total);
  await expect(page.locator('#erro-leitores')).toBeHidden();
  await page.locator('#filtro-leitores').fill('ANTT');
  const leitor=page.locator('#coletores>.leitor:visible');
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
  await page.goto('resources/status.html');
  await expect(page.locator('#erro-cobertura')).toContainText('Banco indisponível');
  await expect(page.locator('#atualizar')).toBeEnabled();
  await page.unroute('**/api.pse?**');
  await page.locator('#atualizar').click();
  await expect(page.locator('#estados tr')).toHaveCount(27);
  await expect(page.locator('#erro-cobertura')).toBeHidden();
});

test('estado: UF sem cadastros e UF inválida',async({page})=>{
  await page.goto('resources/status-estado.html?uf=AC');
  await expect(page.locator('#nome-estado')).toHaveText('Acre (AC)');
  await expect(page.locator('#progresso')).toContainText('0 de 0');
  await expect(page.locator('#mais')).toBeHidden();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await page.goto('resources/status-estado.html?uf=XX');
  await expect(page.locator('#erro-cobertura')).toContainText('27 siglas');
});

test.describe('fontes documentais',()=>{
  test.use({comDocumentacao:true});
  test('documentos lidos mantêm cadastro pendente e erros continuam vermelhos',async({page})=>{
    await page.goto('resources/status.html');
    await page.locator('#filtro-leitores').fill('STTU Natal');
    const leitor=page.locator('#coletores>.leitor:visible');
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
