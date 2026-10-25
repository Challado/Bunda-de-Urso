/* Fecha a aba dos detalhes ou reabre a mesma consulta quando o navegador nao permite fechar. */
(function(){
  "use strict";
  var params = new URLSearchParams(location.search);
  var home = new URL("./", location.href);
  var destino = home;
  try{
    var consulta = new URL(params.get("consulta") || "./", home);
    if (consulta.origin === home.origin && consulta.pathname === home.pathname){
      destino = consulta;
    }
  }catch(e){/* Link incompleto: a home permanece disponivel. */}
  document.querySelectorAll(".voltar-consulta").forEach(function(link){
    link.href = destino.href;
    link.addEventListener("click", function(ev){
      if (ev.button !== 0 || ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.altKey) return;
      if (params.get("nova_aba") !== "1") return;
      ev.preventDefault();
      // O clique abriu esta aba: ao fecha-la, a consulta original continua intacta.
      window.close();
      // Alguns navegadores impedem o fechamento. O link preserva coordenadas e raio.
      setTimeout(function(){ location.assign(destino.href); }, 150);
    });
  });
})();
