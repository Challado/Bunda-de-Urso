const {defineConfig}=require('@playwright/test');
const {projects:projetosFuncionais,...base}=require('./playwright.config.cjs');
const telas=require('./tests/e2e/resolucoes.cjs');
const projetos=[];
for(const browserName of ['chromium','firefox','webkit']){
  for(const tela of telas){
    projetos.push({
      name:browserName+'-'+tela.grupo+'-'+tela.width+'x'+tela.height+'-'+tela.nome,
      metadata:{tela},
      use:{browserName,viewport:{width:tela.width,height:tela.height},
        deviceScaleFactor:tela.dpr,hasTouch:tela.toque,
        // Playwright nao aceita isMobile no Firefox; viewport e toque permanecem.
        isMobile:browserName!=='firefox'&&tela.toque,
        ...(browserName==='chromium'&&process.env.RADAR_TEST_CHROMIUM?{launchOptions:{executablePath:process.env.RADAR_TEST_CHROMIUM}}:{}),
      },
    });
  }
}
module.exports=defineConfig(base,{
  testMatch:'**/layouts.responsivo.spec.cjs',
  testIgnore:[],
  timeout:45000,
  outputDir:'test-results-layouts',
  reporter:[['line'],['html',{outputFolder:'playwright-layout-report',open:'never'}],['json',{outputFile:'test-results-layouts/resumo.json'}]],
  projects:projetos,
});
