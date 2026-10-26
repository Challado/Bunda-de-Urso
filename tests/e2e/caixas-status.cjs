const {expect}=require('@playwright/test');

// A hierarquia precisa aparecer como caixas completas dentro das caixas pais,
// inclusive quando todos os niveis estiverem abertos em uma tela de 320 px.
async function validarCaixasStatus(page){
  const raiz=page.locator('.territorio-federal');
  const estado=raiz.locator('.estado-leitores[data-uf="CE"]');
  const municipio=estado.locator('.municipio-leitores[data-municipio="2304400"]');
  const fonte=municipio.locator('.fonte-leitores');
  const leitor=fonte.locator('.leitor');
  const caixas=[raiz,estado,municipio,fonte,leitor];
  const larguraDisponivel=await page.locator('#coletores').evaluate(n=>n.getBoundingClientRect().width);
  expect((await raiz.boundingBox()).width).toBeGreaterThanOrEqual(larguraDisponivel-1);
  for(let i=0;i<caixas.length;i++){
    const caixa=caixas[i];
    await expect(caixa).toBeVisible();
    await expect(caixa).toHaveCSS('border-top-style','solid');
    const cabecalho=caixa.locator(':scope > summary');
    await expect(cabecalho).toHaveCSS('cursor','pointer');
    const box=await caixa.boundingBox(),titulo=await cabecalho.boundingBox();
    expect(titulo.width).toBeGreaterThanOrEqual(box.width-3);
    expect(titulo.height).toBeGreaterThanOrEqual(44);
    if(i){
      const pai=await caixas[i-1].boundingBox();
      const corpo=caixas[i-1].locator(':scope > .filhos-leitores');
      const padding=await corpo.evaluate(n=>parseFloat(getComputedStyle(n).paddingLeft));
      expect(box.x).toBeGreaterThan(pai.x);
      expect(box.x+box.width).toBeLessThan(pai.x+pai.width);
      expect(box.width).toBeGreaterThanOrEqual(pai.width-padding*2-4);
      expect(await caixa.evaluate(n=>n.parentElement.classList.contains('filhos-leitores'))).toBe(true);
    }
  }
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
}

module.exports={validarCaixasStatus};
