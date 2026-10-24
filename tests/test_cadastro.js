const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../web/resources/cadastro.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function pagina(resposta) {
  const nodes = {}, chamadas = [], eventos = {};
  for (const id of ['camposExpert','dicaModo','res','bt','btGeo','geoInfo']) nodes[id] = {innerHTML:'',textContent:'',disabled:false,addEventListener(){}};
  const elements = {modo:{value:'simplificado'}};
  for (const name of ['identificador','tipo_radar','modelo','latitude','longitude','uf','municipio','via','km','velocidade_geral','sentido','observacoes','contato']) elements[name] = {value:'',required:false};
  const radios = [{addEventListener(event,fn){eventos.modo=fn;}},{addEventListener(){}}];
  nodes.form = {elements,querySelectorAll:()=>radios,addEventListener(event,fn){eventos[event]=fn;}};
  const ctx = {document:{getElementById:id=>nodes[id]},navigator:{},Number,encodeURIComponent,setTimeout,clearTimeout,
    fetch:async(url,options)=>{chamadas.push({url,body:JSON.parse(options.body)});return typeof resposta==='function'?resposta():{status:201,json:async()=>resposta};}};
  vm.runInNewContext(script,ctx);
  const preencher = values => Object.entries(values).forEach(([key,value])=>elements[key].value=value);
  const enviar = async()=>{eventos.submit({preventDefault(){}});await new Promise(setImmediate);};
  return {nodes,elements,chamadas,preencher,enviar,expert(){elements.modo.value='expert';eventos.modo();},simples(){elements.modo.value='simplificado';eventos.modo();}};
}

(async()=>{
  const sucesso = {sucesso:true,resultado:{ok:true,aceitos:1,criados:1,cadastros:[{id:'P-42',proximidade:{raio_metros:150,status:'candidato',campos_complementados:{via:'BR-277'},candidatos:[{id:'P-1',distancia_metros:12,via:'BR-277'}]}}]}};
  const p=pagina(sucesso);
  assert.equal(p.nodes.camposExpert.hidden,true);
  assert.equal(p.nodes.camposExpert.disabled,true);
  assert.equal(p.elements.velocidade_geral.required,true);
  p.preencher({latitude:'-24,9555',longitude:'-53,4552',velocidade_geral:'60',via:'NAO ENVIAR NO SIMPLES'});
  await p.enviar();
  assert.deepEqual(p.chamadas[0].body,{latitude:-24.9555,longitude:-53.4552,velocidade_geral:60});
  assert.match(p.nodes.res.innerHTML,/Cadastro recebido/);
  assert.match(p.nodes.res.innerHTML,/detalhe.html\?id=P-42/);
  assert.match(p.nodes.res.innerHTML,/Dados complementados por proximidade/);
  assert.equal(p.nodes.bt.disabled,false);
  p.expert();
  assert.equal(p.nodes.camposExpert.hidden,false);
  assert.equal(p.elements.latitude.required,false);
  p.preencher({latitude:'',longitude:'',velocidade_geral:'',municipio:'Cascavel',via:'BR-277'});
  await p.enviar();
  assert.deepEqual(p.chamadas[1].body,{municipio:'Cascavel',via:'BR-277'});
  p.simples();
  await p.enviar();
  assert.equal(p.chamadas.length,2);
  assert.match(p.nodes.res.innerHTML,/Informe latitude, longitude e velocidade/);
  for (const values of [{latitude:'NaN',longitude:'-53',velocidade_geral:'60'},{latitude:'-24',longitude:'-53',velocidade_geral:'-60'},{latitude:'-24',longitude:'',velocidade_geral:'60'}]) {
    p.preencher(values); await p.enviar(); assert.equal(p.chamadas.length,2);
  }
  const repetido=pagina({sucesso:true,resultado:{ok:true,aceitos:1,criados:0,ja_cadastrados:1}});
  repetido.preencher({latitude:'-24',longitude:'-53',velocidade_geral:'60'});
  await repetido.enviar();
  assert.match(repetido.nodes.res.innerHTML,/nenhuma duplicata/);
  const erro=pagina(async()=>({status:409,json:async()=>({sucesso:false,erro:{mensagem:'Área bloqueada',detalhes:[{campo:'coordenada',mensagem:'<img src=x onerror=alert(1)>'}]}})}));
  erro.preencher({latitude:'-24',longitude:'-53',velocidade_geral:'60'});
  await erro.enviar();
  assert.match(erro.nodes.res.innerHTML,/Área bloqueada/);
  assert.ok(!erro.nodes.res.innerHTML.includes('<img'));
  assert.equal(erro.nodes.bt.disabled,false);
  const offline=pagina(async()=>{throw Error('offline');});
  offline.preencher({latitude:'-24',longitude:'-53',velocidade_geral:'60'});
  await offline.enviar();
  assert.match(offline.nodes.res.innerHTML,/Não foi possível confirmar/);
  assert.equal(offline.nodes.bt.disabled,false);
  console.log('Cadastro: modos, tres campos, 201/envelope, decimais, proximidade, duplicata, validacao e erros passaram.');
})().catch(error=>{console.error(error);process.exitCode=1;});
