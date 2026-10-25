const {test,expect}=require('./fixtures.cjs');

const {preparar,medidas}=require('./home-layout-ajuda.cjs');

test('poucos radares cabem com mapa reduzido e sem rolagem da pagina',async({page})=>{
  await page.setViewportSize({width:1280,height:900});
  await preparar(page,2);
  await expect(page.locator('#painelResultados')).not.toHaveClass(/recolhivel/);
  await expect.poll(async()=>{const m=await medidas(page);return m.pagina<=m.tela+3;}).toBe(true);
  const m=await medidas(page);
  expect(m.mapa).toBeGreaterThanOrEqual(m.util*.5-1);
  expect(m.mapa).toBeLessThan(m.util);
  await page.screenshot({path:test.info().outputPath('home-poucos-radares.png'),fullPage:true});
});

test('muitos radares usam lista recolhivel com rolagem e preservam mapa minimo',async({page})=>{
  const estado=await preparar(page,60);
  await expect(page.locator('#painelResultados')).toHaveClass(/recolhivel/);
  await expect.poll(async()=>{const m=await medidas(page);return m.conteudo>m.lista&&m.pagina<=m.tela+3;}).toBe(true);
  await page.screenshot({path:test.info().outputPath('home-muitos-radares.png'),fullPage:true});
  const antes=await medidas(page);
  expect(antes.mapa).toBeGreaterThanOrEqual(Math.max(180,antes.util*.5)-1);
  await page.locator('#tituloResultados').click();
  await expect(page.locator('#resultado')).toBeHidden();
  await expect.poll(async()=>(await medidas(page)).mapa).toBeGreaterThan(antes.mapa);
  await page.locator('#tituloResultados').click();
  await expect(page.locator('#resultado')).toBeVisible();
  await expect(page.locator('#resultado tbody tr')).toHaveCount(60);
  estado.quantidade=0;
  await page.locator('#btConsultar').click();
  await expect(page.locator('#resultado tbody tr')).toHaveCount(0);
  await expect(page.locator('#painelResultados')).not.toHaveClass(/recolhivel/);
  await expect(page.locator('#tituloResultados')).toBeHidden();
});

test('limites da API e mudanca de tamanho recalculam layout sem perder radares',async({page})=>{
  await page.setViewportSize({width:1280,height:900});
  await preparar(page,60,{mapa_min_percentual:75,mapa_min_altura_px:200});
  await expect.poll(async()=>{const m=await medidas(page);return Math.abs(m.mapa-m.util*.75)<2;}).toBe(true);
  await page.setViewportSize({width:640,height:360});
  await expect.poll(async()=>(await medidas(page)).mapa).toBeGreaterThanOrEqual(199);
  await expect(page.locator('#resultado tbody tr')).toHaveCount(60);
  await expect.poll(async()=>{const m=await medidas(page);return m.pagina>m.tela;}).toBe(true);
  await page.setViewportSize({width:1280,height:1000});
  await expect.poll(async()=>{const m=await medidas(page);return m.pagina<=m.tela+3;}).toBe(true);
});

test('configuracao indisponivel conserva limites locais e consulta funcional',async({page})=>{
  await preparar(page,60,null);
  await expect(page.locator('#painelResultados')).toHaveClass(/recolhivel/);
  await expect.poll(async()=>{const m=await medidas(page);return Math.abs(m.mapa-Math.max(180,m.util*.5))<2;}).toBe(true);
});
