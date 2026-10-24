const {test,expect}=require('./fixtures.cjs');

test('raio avisa em cada mudança entre nenhum radar e radar encontrado',async({page})=>{
  // Biblioteca real e fixa, sem depender de CDN ou baixar os mapas no teste.
  await page.route('https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',r=>r.fulfill({path:require.resolve('leaflet/dist/leaflet.js'),contentType:'application/javascript'}));
  await page.route('https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',r=>r.fulfill({path:require.resolve('leaflet/dist/leaflet.css'),contentType:'text/css'}));
  await page.route('https://*.tile.openstreetmap.org/**',r=>r.fulfill({status:204}));
  await page.addInitScript(()=>sessionStorage.setItem('radarCowboy','1'));
  // O equipamento da fixture fica a aproximadamente 620 m deste centro.
  await page.goto('index.html?lat=-24.95&lon=-53.4552&raio=200');
  await expect(page.locator('#festa')).toBeVisible();
  await expect(page).toHaveURL(/\/resources\/index.html\?/);
  await page.evaluate(()=>{
    window.avisos={festa:1,problema:0};
    for(const id of ['festa','problema']){
      const el=document.getElementById(id);
      new MutationObserver(mudancas=>{
        for(const m of mudancas){
          if(!String(m.oldValue||'').split(/\s+/).includes('on')&&el.classList.contains('on'))window.avisos[id]++;
        }
      }).observe(el,{attributes:true,attributeFilter:['class'],attributeOldValue:true});
    }
  });
  async function fechar(id){await page.locator('#'+id).click({position:{x:5,y:5}});}
  async function raio(indice,metros){
    const resposta=page.waitForResponse(r=>{
      const u=new URL(r.url());return u.pathname.endsWith('/api.pse')&&u.searchParams.get('rota')==='/api/v1/radares'&&u.searchParams.get('raio')===String(metros);
    });
    await page.locator('#raio').evaluate((el,i)=>{el.value=String(i);el.dispatchEvent(new Event('input'));el.dispatchEvent(new Event('change'));},indice);
    expect((await resposta).status()).toBe(200);
    await expect(page.locator('#barra')).toContainText('Snapshot');
  }
  await fechar('festa');
  await raio(1,500);
  expect(await page.evaluate(()=>window.avisos)).toEqual({festa:1,problema:0});
  await raio(2,1000);
  await expect(page.locator('#problema')).toBeVisible();
  await expect(page.locator('#problema')).toContainText('Você está com problemas, cowboy!');
  await fechar('problema');
  await raio(3,2000);
  expect(await page.evaluate(()=>window.avisos)).toEqual({festa:1,problema:1});
  await raio(2,1000);
  expect(await page.evaluate(()=>window.avisos)).toEqual({festa:1,problema:1});
  await raio(1,500);
  await expect(page.locator('#festa')).toBeVisible();
  await fechar('festa');
  await raio(0,200);
  expect(await page.evaluate(()=>window.avisos)).toEqual({festa:2,problema:1});
  await raio(2,1000);
  await expect(page.locator('#problema')).toBeVisible();
  expect(await page.evaluate(()=>window.avisos)).toEqual({festa:2,problema:2});
});
