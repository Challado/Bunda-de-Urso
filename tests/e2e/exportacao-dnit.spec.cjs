const {test,expect,chromium}=require('@playwright/test');
const {execFile}=require('node:child_process');
const {promisify}=require('node:util');

test('coletor exporta XLSX blob com Chromium e preserva o arquivo',async({browserName},info)=>{
  test.skip(browserName!=='chromium' || info.project.name!=='chromium-desktop',
    'A dependencia do coletor e Chromium; esta exportacao independe do navegador do usuario.');
  const executar=promisify(execFile);
  const resultado=await executar(process.env.RADAR_TEST_PYTHON || 'python3',[
    '-c','from tests.test_dnit_complemento import exportar_blob_real; exportar_blob_real()'
  ],{timeout:28000,env:{...process.env,
    RADAR_TEST_CHROMIUM:process.env.RADAR_TEST_CHROMIUM || chromium.executablePath()}});
  expect(resultado.stderr).toBe('');
});
