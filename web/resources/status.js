'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const numero = n => new Intl.NumberFormat('pt-BR').format(n ?? 0);
  const quantidade = v => v == null ? 'Não informado' : numero(v);
  const nomes = {federal:'Federal',estadual:'Estadual / distrital',municipal:'Municipal',nao_classificado:'Sem classificação'};
  const estadosLeitura = {documentado:'Documentação lida',ok:'Leitura OK',sem_mudanca:'Sem alteração',erro:'Erro na leitura',em_andamento:'Em andamento',interrompido:'Leitura interrompida',nunca_coletado:'Nunca lido'};
  const situacoes = {ativo:'Ativo',inativo:'Inativo',manutencao:'Em manutenção',em_instalacao:'Em instalação',suspenso:'Suspenso',desconhecido:'Não informado'};
  const data = s => {
    if (!s) return 'Ainda não registrada';
    const d = new Date(/(?:Z|[+-]\d\d:\d\d)$/.test(s) ? s : s+'Z');
    return Number.isNaN(d.getTime()) ? s : d.toLocaleString('pt-BR');
  };
  function el(tag, texto, cls) { const n=document.createElement(tag); if(texto!=null)n.textContent=texto;if(cls)n.className=cls;return n; }
  function link(texto, url, interno=false) {
    if(!interno && !/^https?:\/\//i.test(url||''))return el('span',texto);
    const a=el('a',texto);try {const u=new URL(url,location.href);if(!['http:','https:'].includes(u.protocol))return el('span',texto);a.href=u.href;}catch{return el('span',texto);}
    a.target='_blank';a.rel='noopener noreferrer';return a;
  }
  async function api(rota, params={}) {
    const url=new URL('../api.pse',location.href);url.search=new URLSearchParams({rota,...params});
    const abort=new AbortController();const timer=setTimeout(()=>abort.abort(),25000);
    try {
      const r=await fetch(url,{signal:abort.signal,cache:'no-store',headers:{Accept:'application/json'}});
      const doc=await r.json();
      if(!r.ok || !doc.sucesso)throw new Error(doc.erro?.mensagem || 'A consulta falhou (HTTP '+r.status+').');
      return doc.resultado;
    } catch(e) {if(e.name==='AbortError')throw new Error('A consulta demorou demais. Tente atualizar novamente.');throw e;}
    finally{clearTimeout(timer);}
  }
  function erro(id, e) {$(id).hidden=!e;$(id).textContent=e ? 'Não foi possível carregar: '+e.message : '';}
  function totais(d) {
    $('totais').replaceChildren();
    for(const [k,n] of [['total','Total de pontos'],['federal','Federais'],['estadual','Estaduais / distritais'],['municipal','Municipais'],['nao_classificado','Sem classificação']]) {
      const c=el('div',null,'numero');c.append(el('strong',numero(d[k])),el('span',n));$('totais').append(c);
    }
  }
  function celula(tr, valor, numerica=false) {const td=el('td',valor,numerica?'quantidade':null);tr.append(td);return td;}
  async function carregarCobertura() {
    erro('erro-cobertura',null);
    try {
      const d=await api('/api/v1/status/estados');
      const linhas=d.estados.map(e=>{
        const tr=el('tr');celula(tr,e.numero);const th=el('th');th.scope='row';th.append(link(e.nome+' ('+e.uf+')','status-estado.html?uf='+e.uf,true));tr.append(th);
        for(const k of ['federal','estadual','municipal','nao_classificado','total'])celula(tr,numero(e[k]),true);
        return tr;
      });
      $('estados').replaceChildren(...linhas);const total=el('tr');const th=el('th','Total das 27 UFs');th.colSpan=2;th.scope='row';total.append(th);
      for(const k of ['federal','estadual','municipal','nao_classificado','total'])celula(total,numero(d.estados.reduce((s,e)=>s+e[k],0)),true);
      $('total-estados').replaceChildren(total);totais(d.totais);$('criterio').textContent=d.criterio;
      $('sem-uf').hidden=!d.sem_uf.total;$('sem-uf').textContent=numero(d.sem_uf.total)+' ponto(s) sem UF identificada: entram no total nacional e aguardam localização para entrar na tabela.';
      $('atualizado').textContent='Cobertura consultada em '+data(d.gerado_em)+'.';
    } catch(e){erro('erro-cobertura',e);$('atualizado').textContent='Cobertura não atualizada. Use “Atualizar status” para tentar novamente.';}
  }
  function campos(pares) {
    const dl=el('dl',null,'campos');for(const [nome,valor] of pares){const grupo=el('div');grupo.append(el('dt',nome),el('dd',valor??'Não informado'));dl.append(grupo);}return dl;
  }
  function filtrar() {
    const termo=$('filtro-leitores').value.toLocaleLowerCase('pt-BR');let n=0;
    for(const item of $('coletores').children){item.hidden=!item.dataset.busca.includes(termo);if(!item.hidden)n++;}
    $('resumo-leitores').textContent=numero(n)+' de '+numero($('coletores').children.length)+' leitores exibidos.';
  }
  async function carregarLeitores() {
    erro('erro-leitores',null);
    try {
      const d=await api('/api/v1/status/coletores');
      $('coletores').replaceChildren(...d.coletores.map(r=>{
        const box=el('details',null,'leitor'),s=el('summary'),u=r.ultima_tentativa;
        const documental=r.tipo_coleta==='documental';
        const estado=documental&&r.estado==='sem_mudanca'?'Documentação sem alteração':estadosLeitura[r.estado]||r.estado;
        s.append(el('span',r.fonte+' — '+r.recurso+' '),el('span',estado,'selo '+(['erro','interrompido'].includes(r.estado)?'falha':documental?'espera':['ok','sem_mudanca'].includes(r.estado)?'ok':'espera')));
        if(documental)s.append(el('span','Cadastro de radares pendente','selo espera'));
        if(!r.ativo)s.append(el('span','Desativado','selo'));
        if(u?.linhas_rejeitadas>0)s.append(el('span','Com rejeições','selo espera'));
        if(r.leitura_atrasada)s.append(el('span','Leitura atrasada','selo espera'));
        box.append(s);box.dataset.busca=[r.fonte,r.recurso,nomes[r.esfera],estado,r.estado,r.status_integracao,r.descricao_coleta,documental?'cadastro pendente':'',!r.ativo?'desativado':'ativo',r.leitura_atrasada?'atrasada':''].join(' ').toLocaleLowerCase('pt-BR');
        box.append(campos([['Esfera da fonte',nomes[r.esfera]||r.esfera],['Última tentativa',data(u?.iniciada_em)],['Conclusão da tentativa',data(u?.terminada_em)],['Última leitura bem-sucedida',data(r.ultimo_sucesso?.terminada_em)],['Agendamento',!r.ativo?'Desativado':r.agendado?'Automático':'Fora da agenda automática'],['Intervalo entre leituras',r.intervalo_s ? numero(Math.round(r.intervalo_s/60))+' minutos' : 'Não informado'],['Integração',r.status_integracao],['Resposta HTTP',u?.http_status],['Tentativas',u?.tentativas],['Linhas recebidas',u?quantidade(u.linhas_recebidas):null],['Linhas rejeitadas',u?quantidade(u.linhas_rejeitadas):null],['Cadastros criados / alterados',u?quantidade(u.registros_criados)+' / '+quantidade(u.registros_alterados):null]]));
        const ul=el('ul',null,'urls');
        for(const [titulo,url] of [['Página da fonte',r.url_institucional],['Endereço da última tentativa (quando registrado)',r.url_ultima_tentativa],['Recurso cadastrado',r.url_recurso],['Endereço configurado para leitura',r.url_configurada]])if(url){const li=el('li');li.append(el('span',titulo+': '),link(url,url));ul.append(li);}
        box.append(ul);
        if(r.descricao_coleta)box.append(el('p',r.descricao_coleta,'aviso'));
        if(documental&&u)box.append(campos([['Registros de documentação aceitos',quantidade(u.linhas_validas)]]));
        if(r.erro_relatorio_coleta)box.append(el('p',typeof r.erro_relatorio_coleta==='string'?r.erro_relatorio_coleta:JSON.stringify(r.erro_relatorio_coleta),'erro'));
        if(u?.erro_codigo||u?.erro_detalhe)box.append(el('p',[u.erro_codigo,u.erro_detalhe].filter(Boolean).join(': '),'erro'));
        if(r.erros?.length){box.append(el('h3','Problemas encontrados na última leitura'));const lista=el('ul',null,'lista');for(const e of r.erros)lista.append(el('li',e.codigo_erro+': '+e.descricao+' ('+e.severidade+')'));box.append(lista);}
        return box;
      }));
      if(d.erro_agenda||d.erro_relatorio)erro('erro-leitores',new Error([d.erro_agenda?'Agenda: '+d.erro_agenda:null,d.erro_relatorio?'Relatório: '+d.erro_relatorio:null].filter(Boolean).join('; ')));
      $('total-leitores').textContent=numero(d.total);$('atualizado-leitores').textContent='Histórico consultado em '+data(d.gerado_em)+'. Horários no fuso deste dispositivo.';filtrar();
    } catch(e){erro('erro-leitores',e);$('atualizado-leitores').textContent='Histórico não atualizado. Use “Atualizar status” para tentar novamente.';}
  }
  let depois=null,carregados=0;
  const uf=new URLSearchParams(location.search).get('uf')?.toUpperCase();
  async function carregarEstado(mais=false) {
    erro('erro-cobertura',null);$('mais').disabled=true;
    try {
      if(!/^[A-Z]{2}$/.test(uf||''))throw new Error('Informe a UF no endereço, por exemplo: status-estado.html?uf=TO.');
      const d=await api('/api/v1/status/estados/'+uf,{limite:100,depois:mais?depois:0});
      const e=d.estado;
      if(!mais){
        document.title=e.nome+' — Status Radar Brasil';$('nome-estado').textContent=e.nome+' ('+uf+')';totais(e);$('criterio').textContent=d.criterio;
        for(const id of ['municipios','organizacoes']){$(id).replaceChildren(...(d[id].length?d[id].map(v=>el('li',v.nome+' — '+numero(v.pontos)+' ponto(s)')):[el('li','Nenhum cadastro informado.') ]));}
        $('fontes').replaceChildren(...(d.fontes.length?d.fontes.map(f=>{const li=el('li');li.append(link(f.nome,f.url_institucional),el('span',' — '+numero(f.pontos)+' ponto(s) · '+(nomes[f.esfera]||f.esfera)));return li;}):[el('li','Nenhuma fonte vinculada.') ]));
        $('pontos').replaceChildren();carregados=0;
      }
      for(const p of d.pontos){
        const tr=el('tr');celula(tr).append(link(p.id,'detalhe.html?id='+p.id,true));celula(tr,nomes[p.esfera]);celula(tr,p.municipio||'Não informado');celula(tr,[p.via,p.km!=null?'km '+p.km:null].filter(Boolean).join(' · ')||'Não informada');celula(tr,situacoes[p.situacao]||p.situacao||'Não informada');
        const td=celula(tr);td.append(el('div',p.organizacoes.join('; ')||'Responsável não confirmado'),el('small',p.fontes.map(f=>f.nome).join('; '),'suave'));
        if(p.classificacao==='conflitante')td.append(el('div','Esferas divergentes nas fontes.','aviso'));
        $('pontos').append(tr);
      }
      carregados+=d.pontos.length;depois=d.proximo_depois;$('mais').hidden=depois==null;$('progresso').textContent=numero(carregados)+' de '+numero(e.total)+' ponto(s) exibidos.';
      for(const id of ['detalhes-estado','resumos-estado','fontes-estado','radar-estado'])$(id).hidden=false;
      $('atualizado').textContent='Estado consultado em '+data(d.gerado_em)+'.';
    }catch(e){erro('erro-cobertura',e);$('atualizado').textContent='Consulta não concluída. Tente atualizar novamente.';}
    finally{$('mais').disabled=false;}
  }
  const estado=document.body.dataset.pagina==='status-estado';
  async function atualizar() {const b=$('atualizar');b.disabled=true;try{if(estado)await carregarEstado();else await Promise.all([carregarCobertura(),carregarLeitores()]);}finally{b.disabled=false;}}
  $('atualizar').addEventListener('click',atualizar);
  if(estado)$('mais').addEventListener('click',()=>carregarEstado(true));else $('filtro-leitores').addEventListener('input',filtrar);
  atualizar();
})();
