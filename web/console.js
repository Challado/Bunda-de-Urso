/* Radar Brasil — helper de console para a API (api.pse).
 *
 * COMO USAR (no console do navegador, com qualquer pagina do radar aberta):
 *
 *     await import('/openclaw/radar/console.js')
 *
 * (ou, se preferir:  fetch('console.js').then(r=>r.text()).then(eval)  )
 *
 * Depois disso existe o objeto `rb`. A sessao usa o COOKIE do painel
 * (credenciais:'same-origin'); nada de senha fica no codigo.
 *
 * Sem navegador (curl/shell)? Veja docs/CONSOLE.md.
 *
 * Nao ha segredo aqui: este arquivo so embrulha as rotas publicas da API.
 */
(function (w) {
  "use strict";

  var BASE = "api.pse?rota=";
  var TOKEN = null;            // opcional: rb.usarToken('rb_...')
  var rlog = [];               // historico dos ultimos pedidos (depuracao)

  function url(rota, params) {
    var u = BASE + rota;
    if (params) {
      Object.keys(params).forEach(function (k) {
        var v = params[k];
        if (v !== undefined && v !== null && v !== "") {
          u += "&" + encodeURIComponent(k) + "=" + encodeURIComponent(v);
        }
      });
    }
    return u;
  }

  function req(rota, opts) {
    opts = opts || {};
    var init = { method: opts.method || "GET", credentials: "same-origin", headers: {} };
    if (TOKEN) { init.headers["X-Api-Token"] = TOKEN; }
    if (opts.body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(opts.body);
    }
    var alvo = url(rota, opts.params);
    return fetch(alvo, init).then(function (r) {
      return r.text().then(function (t) {
        var b;
        try { b = JSON.parse(t); } catch (e) { b = t; }
        var out = { status: r.status, ok: r.ok, body: b };
        rlog.push({ quando: new Date().toISOString(), rota: rota, status: r.status });
        if (rlog.length > 30) { rlog.shift(); }
        return out;
      });
    });
  }
  function GET(rota, params) { return req(rota, { params: params }); }
  function POST(rota, body, params) { return req(rota, { method: "POST", body: body, params: params }); }
  function PATCH(rota, body) { return req(rota, { method: "PATCH", body: body }); }
  function DEL(rota) { return req(rota, { method: "DELETE" }); }

  var rb = {
    // ---- infraestrutura (se quiser mais controle) ----
    _req: req, _url: url, _log: function () { return rlog.slice(); },
    usarToken: function (t) { TOKEN = t || null; return TOKEN ? "token setado" : "token limpo"; },

    // ---- sessao ----
    login:   function (login, senha) { return POST("/api/v1/login", { login: login, senha: senha }); },
    logout:  function () { return POST("/api/v1/logout", {}); },
    eu:      function () { return GET("/api/v1/gestao/eu"); },
    senha:   function (senhaAtual, senhaNova) { return POST("/api/v1/minha-senha", { senha_atual: senhaAtual, senha_nova: senhaNova }); },

    // ---- consulta publica ----
    radares:   function (p) { return GET("/api/v1/radares", p); },              // p: {lat,lon,raio,limite,...}
    radar:     function (id, p) { return GET("/api/v1/radares/" + id, p); },
    historico: function (id) { return GET("/api/v1/radares/" + id + "/historico"); },
    busca:     function (p) { return GET("/api/v1/radares/busca", p); },        // p: {uf,rodovia,municipio_ibge,...}
    fontes:    function () { return GET("/api/v1/fontes"); },
    status:    function () { return GET("/api/v1/status"); },
    ajuda:     function () { return GET("/api/v1/ajuda"); },
    submeter:  function (dados) { return POST("/api/v1/radares/submeter", dados); },

    // ---- gestao de radares ----
    pendentes: function () { return GET("/api/v1/gestao/pendentes"); },
    gestaoRadar: function (id) { return GET("/api/v1/gestao/radar/" + id); },
    editar:    function (id, campos) { return PATCH("/api/v1/gestao/radar/" + id, campos); },   // {km,observacoes,...}
    verificar: function (id, motivo) { return POST("/api/v1/gestao/radar/" + id + "/verificar", { motivo: motivo }); },
    desabilitar: function (id, motivo) { return POST("/api/v1/gestao/radar/" + id + "/desabilitar", { motivo: motivo }); },
    remover:   function (id, motivo) { return POST("/api/v1/gestao/radar/" + id + "/remover", { motivo: motivo }); },
    historicoGestao: function (id) { return GET("/api/v1/gestao/radar/" + id + "/historico"); },
    vinculo:   function (id, status, motivo) { return POST("/api/v1/gestao/correspondencias/" + id, { status: status, motivo: motivo }); }, // status: oficial_vence|colaborativo_vence

    // ---- bloqueios geograficos (admin) ----
    bloqueios:   function () { return GET("/api/v1/gestao/bloqueios"); },
    bloquear:    function (b) { return POST("/api/v1/gestao/bloqueios", b); },  // {tipo,latitude,longitude,raio_metros,motivo}
    desbloquear: function (id) { return DEL("/api/v1/gestao/bloqueios/" + id); },

    // ---- tokens (admin) ----
    tokens:      function () { return GET("/api/v1/gestao/tokens"); },
    criarToken:  function (nome, escopo) { return POST("/api/v1/gestao/tokens", { nome: nome, escopo: escopo }); },
    revogarToken: function (id) { return POST("/api/v1/gestao/tokens/" + id + "/revogar", {}); },

    // ---- usuarios (admin) ----
    usuarios:      function () { return GET("/api/v1/gestao/usuarios"); },
    criarUsuario:  function (u) { return POST("/api/v1/gestao/usuarios", u); },       // {login,papel,senha?,nome?,email?}
    editarUsuario: function (id, campos) { return PATCH("/api/v1/gestao/usuarios/" + id, campos); }, // {papel?,ativo?}
    resetarSenha:  function (id) { return POST("/api/v1/gestao/usuarios/" + id + "/senha", {}); }
  };

  w.rb = rb;
  w.console.log(
    "%cRadar Brasil%c  helper 'rb' pronto. Ex.: rb.login('admin','...') | rb.pendentes() | rb.senha('atual','nova') | rb.usuarios()",
    "font-weight:bold;color:#c1440e", "color:inherit"
  );
  return rb;
})(window);
