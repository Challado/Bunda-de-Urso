/* Destinos de mapas compartilhados pela consulta e pelos detalhes dos radares. */
(function(global){
  "use strict";
  function esc(s){
    return String(s).replace(/[&<>"']/g,function(c){
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];
    });
  }
  global.RadarMapas = {};
  global.RadarMapas.links = function(latitude, longitude){
    function coordenada(v){
      if (typeof v === "number") return v;
      if (typeof v !== "string") return NaN;
      var s = v.trim().replace(",", ".");
      return /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(s) ? Number(s) : NaN;
    }
    var lat = coordenada(latitude), lon = coordenada(longitude);
    if (!isFinite(lat) || !isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return "";
    var posicao = encodeURIComponent(lat + "," + lon);
    var links = [
      ["https://www.openstreetmap.org/?mlat=" + lat + "&mlon=" + lon + "#map=18/" + lat + "/" + lon, "OpenStreetMap"],
      ["https://www.google.com/maps/search/?api=1&query=" + posicao, "Google Maps"],
      ["https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=" + posicao, "Street View"],
      ["https://www.bing.com/maps?cp=" + lat + "~" + lon + "&lvl=18&style=r", "Bing Mapas"],
      ["https://www.bing.com/maps?cp=" + lat + "~" + lon + "&lvl=18&style=x", "Bing Streetside"]
    ];
    return "<span class='links-mapas'>" + links.map(function(link){
      return "<a href='" + esc(link[0]) + "' target='_blank' rel='noopener noreferrer'>" + link[1] + "</a>";
    }).join("") + "</span>";
  };
})(window);
