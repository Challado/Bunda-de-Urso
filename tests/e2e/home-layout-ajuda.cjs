const {expect}=require('./fixtures.cjs');

async function preparar(page,quantidade,config={mapa_min_percentual:50,mapa_min_altura_px:180}){
  await page.route('https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',r=>r.fulfill({path:require.resolve('leaflet/dist/leaflet.js'),contentType:'application/javascript'}));
  await page.route('https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',r=>r.fulfill({path:require.resolve('leaflet/dist/leaflet.css'),contentType:'text/css'}));
  await page.route('https://*.tile.openstreetmap.org/**',r=>r.fulfill({status:204}));
  const doc=await (await page.request.get('api.pse?rota=/api/v1/radares&lat=-24.9556&lon=-53.4552&raio=2000')).json();
  const ponto=doc.resultado.pontos[0];
  expect(ponto).toBeTruthy();
  const estado={quantidade,erroConsulta:false};
  await page.route('**/api.pse?**',async r=>{
    const rota=new URL(r.request().url()).searchParams.get('rota');
    if(rota==='/api/v1/interface')return r.fulfill({status:config?200:503,json:config?{sucesso:true,resultado:config}:{sucesso:false}});
    if(rota==='/api/v1/radares'&&estado.erroConsulta)return r.fulfill({status:503,json:{sucesso:false,erro:{mensagem:'Falha simulada na consulta'}}});
    if(rota==='/api/v1/radares')return r.fulfill({json:{sucesso:true,resultado:{...doc.resultado,
      pontos:Array.from({length:estado.quantidade},(_,i)=>({...ponto,id:'P-'+(i+1)})),
      total_pontos:estado.quantidade,total_equipamentos:estado.quantidade,retornados:estado.quantidade,proximo_cursor:null}}});
    await r.continue();
  });
  await page.goto('./?lat=-24.9556&lon=-53.4552&raio=2000');
  await expect(page.locator('#resultado tbody tr')).toHaveCount(quantidade);
  const aviso=page.locator(quantidade?'#problema':'#festa');
  await expect(aviso).toBeVisible();
  await aviso.click({position:{x:5,y:5}});
  return estado;
}
async function medidas(page){return page.evaluate(()=>{
  const painel=document.querySelector('#painelResultados'),r=document.querySelector('#resultado');
  const fixos=['header','#controles','#legenda','#barra','footer'].reduce((n,s)=>n+document.querySelector(s).getBoundingClientRect().height,0);
  return {natural:matchMedia('(max-width: 1023px), (pointer: coarse)').matches,
    mapa:document.querySelector('#mapa').getBoundingClientRect().height,util:innerHeight-fixos-2,
    pagina:document.documentElement.scrollHeight,tela:innerHeight,lista:r.clientHeight,conteudo:r.scrollHeight,aberto:painel.open};
});}

module.exports={preparar,medidas};
