const {test,expect}=require('./fixtures.cjs');

async function preparar(page,quantidade,config={mapa_min_percentual:50,mapa_min_altura_px:180}){
  await page.route('https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',r=>r.fulfill({path:require.resolve('leaflet/dist/leaflet.js'),contentType:'application/javascript'}));
  await page.route('https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',r=>r.fulfill({path:require.resolve('leaflet/dist/leaflet.css'),contentType:'text/css'}));
  await page.route('https://*.tile.openstreetmap.org/**',r=>r.fulfill({status:204}));
  const doc=await (await page.request.get('api.pse?rota=/api/v1/radares&lat=-24.9556&lon=-53.4552&raio=2000')).json();
  const ponto=doc.resultado.pontos[0];
  expect(ponto).toBeTruthy();
  const estado={quantidade};
  await page.route('**/api.pse?**',async r=>{
    const rota=new URL(r.request().url()).searchParams.get('rota');
    if(rota==='/api/v1/interface')return r.fulfill({status:config?200:503,json:config?{sucesso:true,resultado:config}:{sucesso:false}});
    if(rota==='/api/v1/radares')return r.fulfill({json:{sucesso:true,resultado:{...doc.resultado,
      pontos:Array.from({length:estado.quantidade},(_,i)=>({...ponto,id:'P-'+(i+1)})),
      total_pontos:estado.quantidade,total_equipamentos:estado.quantidade,retornados:estado.quantidade,proximo_cursor:null}}});
    await r.continue();
  });
  await page.goto('./?lat=-24.9556&lon=-53.4552&raio=2000');
  await expect(page.locator('#resultado tbody tr')).toHaveCount(quantidade);
  await expect(page.locator('#problema')).toBeVisible();
  await page.locator('#problema').click({position:{x:5,y:5}});
  return estado;
}
async function medidas(page){return page.evaluate(()=>{
  const painel=document.querySelector('#painelResultados'),r=document.querySelector('#resultado');
  const fixos=['header','#controles','#legenda','#barra','footer'].reduce((n,s)=>n+document.querySelector(s).getBoundingClientRect().height,0);
  return {mapa:document.querySelector('#mapa').getBoundingClientRect().height,util:innerHeight-fixos-2,
    pagina:document.documentElement.scrollHeight,tela:innerHeight,lista:r.clientHeight,conteudo:r.scrollHeight,aberto:painel.open};
});}

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
