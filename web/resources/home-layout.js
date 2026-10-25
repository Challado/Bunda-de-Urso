/* Altura medida no navegador; configuracao publica recebida somente pela API. */
(function(global){
  'use strict';
  global.RadarLayout={iniciar:function(opcoes){
    var mapa=document.getElementById('mapa');
    var painel=document.getElementById('painelResultados');
    var resultado=document.getElementById('resultado');
    var titulo=document.getElementById('tituloResultados');
    var fixos=[document.querySelector('header'),document.getElementById('controles'),
      document.getElementById('legenda'),document.getElementById('barra'),document.querySelector('footer')];
    var config={mapa_min_percentual:50,mapa_min_altura_px:180};
    // Telas estreitas e dispositivos de toque usam a rolagem natural da pagina.
    var fluxoPagina=global.matchMedia('(max-width: 1023px), (pointer: coarse)');
    var pendente=false,ultimaAbertura=painel.open,alturaAnterior=0;
    function ajustar(){
      pendente=false;
      var aberto=painel.open;
      // Mede a lista inteira mesmo quando recolhida ou com rolagem interna.
      painel.open=true;
      // scrollHeight mede o conteudo sem retirar o limite nem interromper um gesto.
      var alturaLista=resultado.scrollHeight+resultado.offsetHeight-resultado.clientHeight;
      var alturaTela=global.visualViewport?global.visualViewport.height:global.innerHeight;
      var fixo=fixos.reduce(function(total,el){return total+(el?el.getBoundingClientRect().height:0);},0);
      var util=Math.max(0,alturaTela-fixo-2);
      var minimo=Math.max(config.mapa_min_altura_px,util*config.mapa_min_percentual/100);
      var linhas=resultado.querySelectorAll('tbody tr').length;
      var natural=fluxoPagina.matches;
      var recolhivel=!natural&&linhas>0&&alturaLista>util-minimo;
      painel.classList.toggle('recolhivel',recolhivel);
      titulo.textContent='Radares encontrados ('+linhas+')';
      var alturaMapa;
      if(natural){
        painel.open=true;
        resultado.style.maxHeight='none';
        resultado.removeAttribute('tabindex');
        // Nao espreme o mapa para acomodar a lista: os resultados seguem abaixo.
        alturaMapa=Math.max(config.mapa_min_altura_px,Math.min(480,alturaTela*config.mapa_min_percentual/100));
      }else if(recolhivel){
        painel.open=aberto;
        var cabecalho=titulo.getBoundingClientRect().height;
        resultado.style.maxHeight=Math.floor(Math.max(96,util-minimo-cabecalho))+'px';
        resultado.tabIndex=0;
        alturaMapa=aberto?minimo:Math.max(minimo,util-cabecalho);
      }else{
        painel.open=true;
        resultado.style.maxHeight='none';
        resultado.removeAttribute('tabindex');
        alturaMapa=Math.max(minimo,util-alturaLista);
      }
      alturaMapa=Math.max(1,Math.floor(alturaMapa));
      mapa.style.height=alturaMapa+'px';
      if(alturaMapa!==alturaAnterior){
        alturaAnterior=alturaMapa;
        opcoes.mapa.invalidateSize({pan:true,animate:false,debounceMoveend:true});
      }
    }
    function agendar(){
      if(!pendente){pendente=true;global.requestAnimationFrame(ajustar);}
    }
    painel.addEventListener('toggle',function(){
      if(painel.open!==ultimaAbertura){ultimaAbertura=painel.open;agendar();}
    });
    new MutationObserver(agendar).observe(resultado,{childList:true,subtree:true,characterData:true});
    new MutationObserver(agendar).observe(document.getElementById('barra'),{childList:true,subtree:true,characterData:true});
    if(global.ResizeObserver){
      var observador=new ResizeObserver(agendar);
      fixos.concat([resultado]).forEach(function(el){if(el)observador.observe(el);});
    }
    global.addEventListener('resize',agendar);
    fluxoPagina.addEventListener('change',agendar);
    global.addEventListener('load',agendar);
    if(global.visualViewport)global.visualViewport.addEventListener('resize',agendar);
    if(document.fonts&&document.fonts.ready)document.fonts.ready.then(agendar);
    agendar();
    var controle=global.AbortController?new AbortController():null;
    var prazo=global.setTimeout(function(){if(controle)controle.abort();},5000);
    fetch(opcoes.api+'?rota=/api/v1/interface',{cache:'no-store',signal:controle?controle.signal:undefined})
      .then(function(r){if(!r.ok)throw new Error('interface');return r.json();})
      .then(function(doc){
        if(!doc.sucesso||!doc.resultado)return;
        var limites={mapa_min_percentual:[10,90],mapa_min_altura_px:[120,600]};
        Object.keys(limites).forEach(function(chave){
          var valor=Number(doc.resultado[chave]);
          if(Number.isFinite(valor))config[chave]=Math.max(limites[chave][0],Math.min(limites[chave][1],valor));
        });
        agendar();
      }).catch(function(){/* Sem a API, mantem os mesmos limites padrao locais. */})
      .then(function(){global.clearTimeout(prazo);});
    return {ajustar:agendar};
  }};
})(window);
