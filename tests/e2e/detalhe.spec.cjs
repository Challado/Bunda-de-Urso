const {test,expect}=require('./fixtures.cjs');
test.use({comMetrologia:true,processarFila:false});

test('detalhe usa equipamento comum às fontes e preserva suas publicações',async({page,request})=>{
  const response=await request.get('api.pse?rota=/api/v1/radares/P-1&formato=json');
  expect(response.status()).toBe(200);
  const p=(await response.json()).resultado.pontos[0];
  expect(p.id).toBe('P-1');
  expect(p.localizacao.latitude).toBe(-24.9556);
  expect(p.velocidade_leves_kmh).toBe(80);
  const equipamento=p.equipamentos[0];
  expect(equipamento.id).toBe('E-1');
  expect(equipamento.instalacoes).toHaveLength(2);
  expect(equipamento.juncao_metrologica).toBeUndefined();
  expect(equipamento.verificacoes_metrologicas).toHaveLength(1);
  expect(equipamento.verificacoes_metrologicas[0].validade_ate).toBe('2027-06-24');
  const original=(await (await request.get('api.pse?rota=/api/v1/radares/P-2')).json()).resultado.pontos[0];
  expect(original.localizacao.latitude).toBeNull();
  expect(original.equipamentos[0].id).toBe(equipamento.id);
  expect(original.equipamentos[0].verificacoes_metrologicas).toHaveLength(1);
  await page.route('https://unpkg.com/**',r=>r.abort());
  await page.goto('detalhe.html?id=P-1');
  await expect(page.locator('#metrologia')).toContainText('Há publicação do Inmetro/PSIE');
  await expect(page.locator('#metrologia')).toContainText('2027-06-24');
  await expect(page.locator('details.fonte')).toHaveCount(2);
  const inmetro=page.locator('details.fonte').filter({has:page.locator('summary h3',{hasText:'INMETRO'})});
  await expect(inmetro).toContainText('Publicação associada ao instrumento');
  await expect(inmetro).toContainText('24/06/2027');
  expect(await inmetro.evaluate(e=>e.open)).toBe(true);
  await page.getByRole('button',{name:'Recolher fontes',exact:true}).click();
  expect(await inmetro.evaluate(e=>e.open)).toBe(false);
  await page.getByRole('button',{name:'Expandir fontes',exact:true}).click();
  expect(await inmetro.evaluate(e=>e.open)).toBe(true);
  await expect(page.locator('.mapas-principais a')).toHaveCount(3);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});


test.describe('radar sem série na ANTT',()=>{
  test.use({comMetrologia:'cadastral'});
  test('mostra correspondência cadastral do Inmetro sem confirmar identidade física',async({page,request})=>{
    const p=(await (await request.get('api.pse?rota=/api/v1/radares/P-1')).json()).resultado.pontos[0];
    expect(p.localizacao.km).toBe(597.42);
    expect(p.equipamentos[0].numero_serie).toBeNull();
    expect(p.correspondencia_metrologica.estado).toBe('compativel');
    expect(p.correspondencia_metrologica.candidatos[0].numero_serie).toBe('FSC110-0811');
    expect(p.correspondencia_metrologica.candidatos[0].identidade_fisica_confirmada).toBe(false);
    expect(p.correspondencia_metrologica.candidatos[0].verificacoes_metrologicas[0].numero_certificado).toBe('16415173');
    await page.route('https://unpkg.com/**',r=>r.abort());
    await page.goto('detalhe.html?id=P-1');
    await expect(page.locator('#metrologia')).toContainText('Foi encontrada uma correspondência cadastral no Inmetro');
    await expect(page.locator('#metrologia')).toContainText('FSC110-0811');
    await expect(page.locator('#metrologia')).toContainText('16415173');
    await expect(page.locator('#metrologia')).toContainText('2027-05-03');
    await expect(page.locator('#metrologia')).not.toContainText('Não foi possível relacionar');
    const fonte=page.locator('details.fonte').filter({has:page.locator('summary h3',{hasText:'INMETRO'})});
    await expect(fonte).toContainText('Publicação com correspondência cadastral');
    await expect(fonte).toContainText('16176985');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  });
});
