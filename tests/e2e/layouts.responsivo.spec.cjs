const {test,expect}=require('./fixtures.cjs');
const {preparar,medidas}=require('./home-layout-ajuda.cjs');

function tela(info){return info.project.metadata.tela;}
async function acionar(locator,info){if(tela(info).toque)await locator.tap();else await locator.click();}
async function semOverflowHorizontal(page){
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);
}
async function capturar(page,info,nome){
  await page.screenshot({path:info.outputPath(nome+'.png'),fullPage:true});
  await info.attach(nome+'-medidas',{body:Buffer.from(JSON.stringify({tela:tela(info),...(await medidas(page))},null,2)),contentType:'application/json'});
}
async function rolarLista(page,browserName,info){
  const lista=page.locator('#resultado');
  await lista.scrollIntoViewIfNeeded();
  const pos=await lista.boundingBox();
  const y=Math.min(pos.y+pos.height/2,page.viewportSize().height-10);
  const antes=await page.evaluate(()=>scrollY);
  if(browserName==='chromium'&&tela(info).toque){
    const cdp=await page.context().newCDPSession(page);
    try{
      const x=Math.round(pos.x+pos.width/2);
      await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y:Math.round(y)}]});
      for(let passo=1;passo<=8;passo++){
        await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x,y:Math.round(y-120*passo/8)}]});
        await new Promise(resolve=>setTimeout(resolve,16));
      }
      await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
    }finally{await cdp.detach();}
  }else if(browserName==='webkit'&&tela(info).toque){
    // Playwright nao oferece roda do mouse no WebKit mobile; usa teclado real.
    await lista.focus();
    await page.keyboard.press('PageDown');
  }else{
    await lista.hover({position:{x:pos.width/2,y:pos.height/2}});
    await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    await page.mouse.wheel(0,350);
  }
  await expect.poll(()=>lista.evaluate(el=>el.scrollTop)).toBeGreaterThan(10);
  // Rolar a lista nao deve mover a pagina por tras dela.
  await expect.poll(()=>page.evaluate(()=>scrollY)).toBe(antes);
}

test('um radar, controles e links cabem na largura e preservam mapa legivel',async({page},info)=>{
  const estado=await preparar(page,1);
  await semOverflowHorizontal(page);
  if(tela(info).width>=768&&tela(info).height>=720)await expect(page.locator('#painelResultados')).not.toHaveClass(/recolhivel/);
  const m=await medidas(page);
  expect(m.mapa).toBeGreaterThanOrEqual(179);
  if(!tela(info).rolaPagina)expect(m.pagina).toBeLessThanOrEqual(m.tela+3);
  await acionar(page.locator('#btConsultar'),info);
  await expect(page.locator('#resultado tbody tr')).toHaveCount(estado.quantidade);
  await page.context().grantPermissions(['geolocation']);
  await page.context().setGeolocation({latitude:-24.9556,longitude:-53.4552});
  for(const id of ['btLocal','btAqui']){
    const resposta=page.waitForResponse(r=>new URL(r.url()).searchParams.get('rota')==='/api/v1/radares');
    await acionar(page.locator('#'+id),info);
    expect((await resposta).status()).toBe(200);
    await expect(page.locator('#barra')).toContainText('Snapshot');
    await expect(page.locator('#resultado tbody tr')).toHaveCount(1);
    await expect(page.locator('#problema')).toBeHidden();
  }
  await capturar(page,info,'home-um-radar');
});

test('lista longa rola de verdade, permite teclado e recolhe sem perder radares',async({page,browserName},info)=>{
  await preparar(page,60);
  await expect(page.locator('#painelResultados')).toHaveClass(/recolhivel/);
  await expect.poll(async()=>{const m=await medidas(page);return m.conteudo>m.lista;}).toBe(true);
  await semOverflowHorizontal(page);
  const m=await medidas(page);
  expect(m.mapa).toBeGreaterThanOrEqual(Math.max(180,m.util*.5)-1);
  if(tela(info).rolaPagina)expect(m.pagina).toBeGreaterThan(m.tela);
  else expect(m.pagina).toBeLessThanOrEqual(m.tela+3);
  await rolarLista(page,browserName,info);
  const lista=page.locator('#resultado');
  await lista.focus();
  const antes=await lista.evaluate(el=>el.scrollTop);
  // Recalcular a altura nao pode jogar o leitor de volta ao inicio da lista.
  await page.evaluate(()=>new Promise(resolve=>{window.dispatchEvent(new Event('resize'));requestAnimationFrame(()=>requestAnimationFrame(resolve));}));
  await expect.poll(()=>lista.evaluate(el=>el.scrollTop)).toBe(antes);
  await page.keyboard.press('PageDown');
  await expect.poll(()=>lista.evaluate(el=>el.scrollTop)).toBeGreaterThan(antes);
  // Ultimo cadastro continua alcancavel pela rolagem da regiao.
  const ultimo=lista.locator('tbody tr').last();
  await ultimo.locator('a').scrollIntoViewIfNeeded();
  await expect(ultimo.locator('a')).toBeInViewport();
  await ultimo.locator('td').last().scrollIntoViewIfNeeded();
  await expect(ultimo.locator('td').last()).toBeInViewport();
  await acionar(page.locator('#tituloResultados'),info);
  await expect(lista).toBeHidden();
  await acionar(page.locator('#tituloResultados'),info);
  await expect(lista).toBeVisible();
  await expect(lista.locator('tbody tr')).toHaveCount(60);
  await capturar(page,info,'home-lista-longa');
});

test('pagina so rola quando necessario e rodape permanece alcancavel',async({page,browserName},info)=>{
  await preparar(page,60);
  if(browserName==='webkit'&&tela(info).toque){
    await page.touchscreen.tap(4,4);
    await page.keyboard.press('PageDown');
  }else{
    await page.mouse.move(4,4);
    await page.mouse.wheel(0,450);
  }
  if(tela(info).rolaPagina)await expect.poll(()=>page.evaluate(()=>scrollY)).toBeGreaterThan(0);
  else await expect.poll(()=>page.evaluate(()=>scrollY)).toBe(0);
  const contato=page.getByRole('link',{name:'Contato',exact:true});
  await contato.scrollIntoViewIfNeeded();
  await expect(contato).toBeInViewport();
  await expect(contato).toHaveAttribute('href','https://servidor.lucas.inf.br/site/contato');
  await semOverflowHorizontal(page);
});

test('zerar a busca limpa lista, muda aviso e recupera espaco do mapa',async({page},info)=>{
  const estado=await preparar(page,60);
  estado.quantidade=0;
  await acionar(page.locator('#btConsultar'),info);
  await expect(page.locator('#festa')).toBeVisible();
  await page.locator('#festa').click({position:{x:5,y:5}});
  await expect(page.locator('#painelResultados')).not.toHaveClass(/recolhivel/);
  await expect(page.locator('#tituloResultados')).toBeHidden();
  await expect(page.locator('#resultado tbody tr')).toHaveCount(0);
  estado.quantidade=60;
  await page.locator('#raio').press('ArrowRight');
  await expect(page.locator('#problema')).toBeVisible();
  await page.locator('#problema').click({position:{x:5,y:5}});
  estado.quantidade=61;
  await page.locator('#raio').press('ArrowRight');
  await expect(page.locator('#resultado tbody tr')).toHaveCount(61);
  await expect(page.locator('#problema')).toBeHidden();
  await semOverflowHorizontal(page);
});

test('orientacao, viewport reduzido e configuracao personalizada recalculam o mapa',async({page},info)=>{
  const original=page.viewportSize();
  await preparar(page,60,{mapa_min_percentual:65,mapa_min_altura_px:220});
  for(const tamanho of [{width:original.height,height:original.width},{width:original.width,height:Math.max(300,Math.floor(original.height*.55))},original]){
    await page.setViewportSize(tamanho);
    await expect.poll(async()=>{const m=await medidas(page);return Math.abs(m.mapa-Math.max(220,m.util*.65))<2;}).toBe(true);
    await expect(page.locator('#resultado tbody tr')).toHaveCount(60);
    await semOverflowHorizontal(page);
  }
  await capturar(page,info,'home-apos-redimensionar');
});

test('falhas da configuracao e consulta mantem controles e recuperacao funcionais',async({page},info)=>{
  const estado=await preparar(page,60,null);
  await expect.poll(async()=>{const m=await medidas(page);return Math.abs(m.mapa-Math.max(180,m.util*.5))<2;}).toBe(true);
  estado.erroConsulta=true;
  await acionar(page.locator('#btConsultar'),info);
  await expect(page.locator('#resultado')).toContainText('Erro de rede');
  await expect(page.locator('#painelResultados')).not.toHaveClass(/recolhivel/);
  await expect(page.locator('#lat')).toHaveValue('-24.9556');
  await expect(page.locator('#btConsultar')).toBeEnabled();
  estado.erroConsulta=false;
  await acionar(page.locator('#btConsultar'),info);
  await expect(page.locator('#resultado tbody tr')).toHaveCount(60);
  await expect(page.locator('#painelResultados')).toHaveClass(/recolhivel/);
  await semOverflowHorizontal(page);
});

test('cadastro simplificado recebe protocolo e permite abrir os detalhes em cada tela',async({page},info)=>{
  await preparar(page,1);
  await acionar(page.getByRole('link',{name:'Cadastrar radar',exact:true}),info);
  await expect(page).toHaveURL(/\/cadastro.html$/);
  await expect(page.locator('#camposExpert')).toBeHidden();
  await page.locator('[name=latitude]').fill('-24,9555');
  await page.locator('[name=longitude]').fill('-53,4552');
  await page.locator('[name=velocidade_geral]').fill('60');
  const resposta=page.waitForResponse(r=>r.url().includes('/api/v1/radares/submeter')&&r.request().method()==='POST');
  await acionar(page.getByRole('button',{name:'Enviar cadastro',exact:true}),info);
  const recebida=await resposta;
  expect(recebida.status()).toBe(202);
  const protocolo=(await recebida.json()).resultado.protocolo;
  await expect.poll(async()=>{
    const r=await page.request.get('api.pse?rota=/api/v1/radares/envios/'+protocolo);
    return (await r.json()).resultado.estado;
  }).toBe('processado');
  const atual=await (await page.request.get('api.pse?rota=/api/v1/radares/envios/'+protocolo)).json();
  await page.goto('detalhe.html?id='+atual.resultado.resultado.cadastros[0].id);
  await expect(page.locator('h1')).toContainText('Radar');
  await semOverflowHorizontal(page);
  await page.getByRole('link',{name:/voltar à consulta/}).first().click();
  await expect(page).toHaveURL(/\/openclaw\/radar\/$/);
});

test('status permite rolar estados, abrir detalhes e recolher leitores',async({page},info)=>{
  await preparar(page,1);
  await page.goto('status.html');
  await expect(page.locator('#estados tr')).toHaveCount(27);
  const estado=page.getByRole('link',{name:'Paraná (PR)'});
  await estado.scrollIntoViewIfNeeded();
  const nova=page.waitForEvent('popup');
  await acionar(estado,info);
  const aba=await nova;
  await expect(aba.locator('#nome-estado')).toHaveText('Paraná (PR)');
  await semOverflowHorizontal(aba);
  await aba.close();
  const resumo=page.locator('#leituras>summary');
  await acionar(resumo,info);
  await expect(page.locator('#filtro-leitores')).toBeHidden();
  await acionar(resumo,info);
  await expect(page.locator('#filtro-leitores')).toBeVisible();
  await semOverflowHorizontal(page);
});
