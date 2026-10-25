/* Painel de operacao da rede; segredos e downloads ficam no servidor. */
(function(global){
  'use strict';
  var opts,cursores={cadastros:0,fontes:0},ocupado=false;
  function el(id){return document.getElementById('tr'+id);}
  function mensagem(texto){el('Mensagem').textContent=texto;}
  function erro(o){return o.body&&o.body.erro?o.body.erro.mensagem:'Falha HTTP '+o.status;}
  async function req(rota,config){
    var o=await opts.req('/api/v1/gestao/traseiro'+rota,config);
    if(o.status!==200)throw new Error(erro(o));
    return o.body.resultado;
  }
  function dados(doc){return '<pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+opts.esc(JSON.stringify(doc,null,2))+'</pre>';}
  async function listar(tipo){
    var r=await req('/'+tipo,{query:'depois='+cursores[tipo]+'&limite=50'});
    cursores[tipo]=r.depois;
    var container=el(tipo==='cadastros'?'Cadastros':'Fontes');
    if(!r.itens.length){container.textContent='Nenhum item nesta página.';return;}
    container.innerHTML=r.itens.map(function(c){
      var h='<details class="trItem"><summary>'+opts.esc(tipo==='cadastros'?'Posição '+c.id+' — '+c.estado:c.documento.nome||'Fonte '+c.id)+'</summary>';
      h+='<p>Origem: '+opts.esc(c.instancia_nome||c.origem)+' · Revisão '+c.revisao+(c.acao==='retirar'?' · retirada anunciada':'')+'</p>'+dados(c.documento);
      if(tipo==='cadastros'&&c.estado==='pendente'&&opts.ehModerador())h+='<form data-cadastro="'+c.id+'" data-evento="'+c.evento_id+'"><label>Como você conferiu a posição? <input name="motivo" required minlength="5" maxlength="2000" style="max-width:100%"></label><button type="submit" name="acao" value="aprovar">Validar e publicar</button> <button type="submit" name="acao" value="rejeitar" class="sec">Rejeitar</button></form>';
      if(tipo==='fontes')h+='<p>Leitura local: '+(c.ativo?'ativada':'desativada')+'. Último sucesso: '+opts.esc(c.ultimo_sucesso||'nenhum')+'</p>'+(c.ultimo_erro?'<p>'+opts.esc(c.ultimo_erro)+'</p>':'')+(opts.ehAdmin()?'<button type="button" data-fonte="'+c.id+'" data-evento="'+c.evento_id+'" data-ativo="'+(!c.ativo)+'">'+(c.ativo?'Desativar':'Ativar leitura nesta instância')+'</button>':'');
      return h+'</details>';
    }).join('');
    container.querySelectorAll('form[data-cadastro]').forEach(function(form){form.onsubmit=async function(ev){
      ev.preventDefault();if(ocupado)return;ocupado=true;
      try{await req('/cadastros/'+form.dataset.cadastro,{method:'POST',body:{acao:ev.submitter.value,motivo:form.elements.motivo.value,evento_id:Number(form.dataset.evento)}});mensagem('Decisão registrada.');cursores.cadastros=0;await listar('cadastros');}
      catch(e){mensagem(e.message);}finally{ocupado=false;}
    };});
    container.querySelectorAll('button[data-fonte]').forEach(function(bt){bt.onclick=async function(){
      bt.disabled=true;
      try{await req('/fontes/'+bt.dataset.fonte,{method:'PATCH',body:{ativo:bt.dataset.ativo==='true',evento_id:Number(bt.dataset.evento)}});cursores.fontes=0;await listar('fontes');mensagem('Leitura local atualizada.');}
      catch(e){mensagem(e.message);bt.disabled=false;}
    };});
  }
  async function carregar(opcoes){
    opts=opcoes;cursores={cadastros:0,fontes:0};mensagem('Consultando a rede…');
    try{
      var r=await req('');
      el('Resumo').textContent=(r.habilitado?'Rede ativada':'Rede desativada no radar.conf')+' · '+r.pendentes+' posições pendentes · '+r.eventos+' eventos · '+r.outbox+' posições aguardando envio.';
      el('Instancias').innerHTML=r.instancias.length?r.instancias.map(function(p){
        return '<div style="overflow-wrap:anywhere"><p><b>'+opts.esc(p.nome)+'</b> — '+opts.esc(p.estado)+'<br>'+opts.esc(p.api_url)+'<br>Intervalo mínimo: '+p.intervalo_segundos+' s · Falhas consecutivas: '+p.falhas+' · Último contato: '+opts.esc(p.ultimo_contato||'ainda não sincronizado')+(p.pausa_inicio?'<br>Parada anunciada: '+opts.esc(p.pausa_inicio)+' até '+opts.esc(p.pausa_fim||'sem previsao de retorno'):'')+(p.ultimo_erro?'<br>'+opts.esc(p.ultimo_erro):'')+'</p>'+(opts.ehAdmin()?['ativo','inativo','bloqueado'].filter(function(s){return s!==p.estado;}).map(function(s){return '<button type="button" class="sec" data-par="'+p.uuid+'" data-estado="'+s+'">'+({ativo:'Reativar',inativo:'Inativar',bloqueado:'Bloquear'})[s]+'</button>';}).join(' '):'')+'</div>';
      }).join(''):'<p>Nenhuma instância cadastrada. Configure uma API inicial em traseiro.pares; o cron fará o registro e descobrirá outros pares.</p>';
      el('Instancias').querySelectorAll('button[data-par]').forEach(function(bt){bt.onclick=async function(){
        bt.disabled=true;
        try{await req('/instancias/'+bt.dataset.par,{method:'PATCH',body:{estado:bt.dataset.estado}});await carregar(opts);}
        catch(e){mensagem(e.message);bt.disabled=false;}
      };});
      el('Ensinar').hidden=!opts.ehAdmin();
      await Promise.all([listar('cadastros'),listar('fontes')]);mensagem('Rede atualizada.');
    }catch(e){mensagem(e.message);}
  }
  global.RadarTraseiro={carregar:carregar};
  el('Recarregar').onclick=function(){carregar(opts);};
  ['Cadastros','Fontes'].forEach(function(nome){el('Mais'+nome).onclick=function(){listar(nome.toLowerCase()).catch(function(e){mensagem(e.message);});};});
  el('Ensinar').onsubmit=async function(ev){
    ev.preventDefault();var bt=this.querySelector('button');bt.disabled=true;
    try{await req('/fontes',{method:'POST',body:{chave:this.elements.chave.value,receita:JSON.parse(this.elements.receita.value)}});cursores.fontes=0;await listar('fontes');mensagem('Fonte compartilhada; leitura permanece desativada.');}
    catch(e){mensagem(e.message);}finally{bt.disabled=false;}
  };
})(window);
