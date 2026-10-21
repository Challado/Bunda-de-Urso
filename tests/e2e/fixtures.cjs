const {test:base, expect} = require('@playwright/test');
const {spawn} = require('node:child_process');
const path = require('node:path');
const readline = require('node:readline');
const {once} = require('node:events');

const test = base.extend({
  processarFila: [true, {option:true}],
  radarServer: async ({processarFila},use) => {
    const child=spawn(process.env.RADAR_TEST_PYTHON || 'python3', [path.join(__dirname,'servidor.py'),...(processarFila?[]:['--sem-fila'])], {stdio:['ignore','pipe','pipe']});
    let stderr='';child.stderr.on('data',chunk=>{stderr+=chunk.toString();});
    const lines=readline.createInterface({input:child.stdout});
    let timer;
    try {
      const url=await new Promise((resolve,reject)=>{
        timer=setTimeout(()=>reject(new Error('Servidor de teste nao iniciou: '+stderr)),15000);
        lines.once('line',line=>{try{resolve(JSON.parse(line).url);}catch(e){reject(e);}});
        child.once('error',reject);
        child.once('exit',code=>reject(new Error('Servidor terminou ('+code+'): '+stderr)));
      });
      clearTimeout(timer);
      await use(url);
    } finally {
      clearTimeout(timer);lines.close();
      if(child.exitCode===null){
        const exited=once(child,'exit');child.kill('SIGTERM');
        const force=setTimeout(()=>child.kill('SIGKILL'),12000);
        await exited;clearTimeout(force);
      }
    }
  },
  baseURL: async ({radarServer},use) => use(radarServer),
  semErrosJavaScript: [async ({page},use) => {
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await use();expect(errors).toEqual([]);
  }, {auto:true}],
});
module.exports={test,expect};
