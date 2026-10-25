const {test,expect}=require('./fixtures.cjs');

test('home abre no prefixo do site e usa resources apenas para arquivos de apoio',async({page})=>{
  await page.route('https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',r=>r.fulfill({path:require.resolve('leaflet/dist/leaflet.js'),contentType:'application/javascript'}));
  await page.route('https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',r=>r.fulfill({path:require.resolve('leaflet/dist/leaflet.css'),contentType:'text/css'}));
  await page.route('https://*.tile.openstreetmap.org/**',r=>r.fulfill({status:204}));
  const respostas=[];
  page.on('response',r=>{if(r.url().includes('/openclaw/radar/'))respostas.push(r);});
  const resposta=await page.goto('./');
  expect(resposta.status()).toBe(200);
  await expect(page).toHaveURL(/\/openclaw\/radar\/$/);
  await expect(page).toHaveTitle(/Radar Brasil/);
  await expect(page.locator('img.logo')).toHaveAttribute('src','resources/bunda-de-urso.png');
  await expect.poll(()=>page.locator('img.logo').evaluate(img=>img.complete&&img.naturalWidth>0)).toBe(true);
  expect((await page.request.get('resources/municipios.json')).status()).toBe(200);
  await page.getByRole('link',{name:'Cadastrar radar'}).click();
  await expect(page).toHaveURL(/\/openclaw\/radar\/cadastro.html$/);
  await expect(page.locator('#bt')).toBeVisible();
  expect(respostas.filter(r=>r.status()>=400).map(r=>r.url())).toEqual([]);
});
