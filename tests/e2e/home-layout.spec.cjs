const {test,expect}=require('./fixtures.cjs');

const {preparar,medidas,conferirMapas}=require('./home-layout-ajuda.cjs');

test('poucos radares preservam mapa legivel e cabem no PC',async({page})=>{
  await page.setViewportSize({width:1280,height:900});
  await preparar(page,2);
  await expect(page.locator('#painelResultados')).not.toHaveClass(/recolhivel/);
  if(!(await medidas(page)).natural)await expect.poll(async()=>{const m=await medidas(page);return m.pagina<=m.tela+3;}).toBe(true);
  const m=await medidas(page);
  expect(m.mapa).toBeGreaterThanOrEqual(m.util*.5-1);
  expect(m.mapa).toBeLessThan(m.util);
  await page.screenshot({path:test.info().outputPath('home-poucos-radares.png'),fullPage:true});
});

test('muitos radares rolam na pagina mobile ou na lista recolhivel do PC',async({page})=>{
  const estado=await preparar(page,60);
  if((await medidas(page)).natural){
    await expect(page.locator('#painelResultados')).not.toHaveClass(/recolhivel/);
    await expect.poll(async()=>{const m=await medidas(page);return m.conteudo<=m.lista+1&&m.pagina>m.tela;}).toBe(true);
  }else{
    await expect(page.locator('#painelResultados')).toHaveClass(/recolhivel/);
    await expect.poll(async()=>{const m=await medidas(page);return m.conteudo>m.lista&&m.pagina<=m.tela+3;}).toBe(true);
    const antes=await medidas(page);
    expect(antes.mapa).toBeGreaterThanOrEqual(Math.max(180,antes.util*.5)-1);
    await page.locator('#tituloResultados').click();
    await expect(page.locator('#resultado')).toBeHidden();
    await expect.poll(async()=>(await medidas(page)).mapa).toBeGreaterThan(antes.mapa);
    await page.locator('#tituloResultados').click();
    await expect(page.locator('#resultado')).toBeVisible();
  }
  await page.screenshot({path:test.info().outputPath('home-muitos-radares.png'),fullPage:true});
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
  await expect.poll(async()=>{const m=await medidas(page);return Math.abs(m.mapa-(m.natural?Math.min(480,m.tela*.75):m.util*.75))<2;}).toBe(true);
  await page.setViewportSize({width:640,height:360});
  await expect.poll(async()=>(await medidas(page)).mapa).toBeGreaterThanOrEqual(199);
  await expect(page.locator('#resultado tbody tr')).toHaveCount(60);
  await expect.poll(async()=>{const m=await medidas(page);return m.pagina>m.tela;}).toBe(true);
  await page.setViewportSize({width:1280,height:1000});
  await expect.poll(async()=>{const m=await medidas(page);return m.natural?m.pagina>m.tela:m.pagina<=m.tela+3;}).toBe(true);
});

test('configuracao indisponivel conserva limites locais e consulta funcional',async({page})=>{
  await preparar(page,60,null);
  if((await medidas(page)).natural)await expect(page.locator('#painelResultados')).not.toHaveClass(/recolhivel/);
  else await expect(page.locator('#painelResultados')).toHaveClass(/recolhivel/);
  await expect.poll(async()=>{const m=await medidas(page);return Math.abs(m.mapa-Math.max(180,m.natural?Math.min(480,m.tela*.5):m.util*.5))<2;}).toBe(true);
});


test('snapshot sem resumo redundante e mapas acompanham o local consultado',async({page})=>{
  await preparar(page,0);
  await expect(page.locator('#barra')).toHaveText('Snapshot 2026-10-25T15:16:38+00:00');
  await expect(page.locator('#resultado')).toBeEmpty();
  await conferirMapas(page.locator('#mapasConsulta'),-24.9556,-53.4552);
  await page.locator('#lat').fill('-16.32712');
  await page.locator('#lon').fill('-51.35782');
  await page.locator('#btConsultar').click();
  await conferirMapas(page.locator('#mapasConsulta'),-16.32712,-51.35782);
  await page.locator('.leaflet-overlay-pane path[stroke="#12508f"][stroke-width="3"]').click();
  await conferirMapas(page.locator('.leaflet-popup-content'),-16.32712,-51.35782);
  // Abre efetivamente outra aba sem depender dos provedores externos.
  await page.context().route('https://www.google.com/maps/**',r=>r.fulfill({body:'Mapa de teste',contentType:'text/plain'}));
  const nova=page.waitForEvent('popup');
  await page.locator('.leaflet-popup-content').getByRole('link',{name:'Google Maps',exact:true}).click();
  const mapa=await nova;
  await expect(mapa).toHaveURL(/query=-16.32712%2C-51.35782/);
  await mapa.close();
});

test('icone do urso volta a raiz da home em todas as paginas',async({page})=>{
  await preparar(page,1);
  for(const caminho of ['./','detalhe.html?id=P-1','cadastro.html','gestao.html','usuarios.html','status.html','status-estado.html?uf=PR']){
    await page.goto(caminho);
    const inicio=page.getByRole('link',{name:'Voltar à home',exact:true});
    await expect(inicio.locator('img')).toHaveAttribute('src','resources/bunda-de-urso.png');
    await inicio.click();
    await expect(page).toHaveURL(/\/openclaw\/radar\/$/);
  }
});
