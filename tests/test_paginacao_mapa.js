// ##-- BUNDITA DE URSO #{23} -- Verificar paginas completas e consultas concorrentes evita ocultar marcacoes na interface. ##
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const html = fs.readFileSync(path.join(__dirname, "../web/index.html"), "utf8");
const trecho = html.slice(html.indexOf("  var consultaAtual = null;"),
  html.indexOf("  function usarLocalizacao(){"));

function resposta(ids, proximo = null, total = ids.length) {
  return {ok: true, json: async () => ({sucesso: true,
    resultado: {pontos: ids.map(id => ({id})), total_pontos: total,
      proximo_cursor: proximo, retornados: ids.length}})};
}
function contexto(fetch) {
  const renders = [], festas = [], avisos = [];
  const ctx = {fetch, AbortController, API: "/api", renders, festas, avisos,
    elRes: {}, elBarra: {}, camadaPts: {clearLayers() {}}, marcaEu: null,
    map: {removeLayer() {}}, ultimo: null,
    L: {circleMarker: () => ({addTo() {return this;}, bindPopup() {return this;}})},
    desenharCirculo() {}, enquadrar() {}, escapeHtml: String,
    render: (meta, pontos) => renders.push({meta, pontos}),
    festa: () => festas.push(true), problemaCowboy: n => avisos.push(n)};
  vm.runInNewContext(trecho, ctx);
  return ctx;
}

async function main() {
  const ids = Array.from({length: 2005}, (_, i) => "P-" + i);
  const urls = [];
  const ctx = contexto(async url => {
    urls.push(url);
    const cursor = Number(new URL(url, "https://exemplo.invalid").searchParams.get("cursor") || 0);
    return resposta(ids.slice(cursor, cursor + 1000), cursor + 1000 < ids.length ? String(cursor + 1000) : null, ids.length);
  });
  await ctx.consultar(-23.55, -46.63, 200000);
  assert.equal(urls.length, 3);
  assert.ok(urls.every(url => url.includes("limite=1000")));
  assert.equal(ctx.renders.at(-1).pontos.length, 2005);
  assert.equal(ctx.renders.at(-1).meta.retornados, 2005);
  assert.equal(ctx.renders.at(-1).meta.proximo_cursor, null);
  assert.deepEqual(ctx.avisos, [2005]);

  let pagina = 0;
  const repetidos = contexto(async () => pagina++ === 0 ? resposta(["A", "B"], "2", 3) : resposta(["B", "C"], null, 3));
  const unido = await repetidos.carregarPaginas("/api?", () => {}, new AbortController().signal);
  assert.deepEqual(Array.from(unido.pontos, p => p.id), ["A", "B", "C"]);

  const ciclo = contexto(async () => resposta(["A"], "1", 2));
  await assert.rejects(ciclo.carregarPaginas("/api?", () => {}, new AbortController().signal), /repetiu/);

  const http = contexto(async () => ({ok: false, status: 503}));
  await assert.rejects(http.carregarPaginas("/api?", () => {}, new AbortController().signal), /HTTP 503/);

  let liberar;
  const abortada = contexto(() => new Promise(resolve => {liberar = resolve;}));
  const controller = new AbortController();
  let chamadas = 0;
  const pendente = abortada.carregarPaginas("/api?", () => {chamadas++;}, controller.signal);
  controller.abort(); liberar(resposta(["VELHA"]));
  await assert.rejects(pendente, e => e.name === "AbortError");
  assert.equal(chamadas, 0);

  let antiga;
  let requisicoes = 0;
  const concorrentes = contexto(() => ++requisicoes === 1 ? new Promise(resolve => {antiga = resolve;}) : Promise.resolve(resposta(["NOVA"])));
  const primeira = concorrentes.consultar(0, 0, 1000);
  await concorrentes.consultar(1, 1, 1000);
  antiga(resposta(["VELHA"])); await primeira;
  assert.deepEqual(concorrentes.renders.map(r => Array.from(r.pontos, p => p.id)), [["NOVA"]]);
  assert.deepEqual(concorrentes.avisos, [1]);

  let n = 0;
  const parcial = contexto(async () => ++n === 1 ? resposta(["A"], "1", 2) : {ok: false, status: 500});
  await parcial.consultar(0, 0, 1000);
  assert.equal(parcial.renders.length, 1);
  assert.equal(parcial.renders[0].meta.proximo_cursor, "1");
  assert.deepEqual(parcial.avisos, []);
  assert.deepEqual(parcial.festas, []);
  assert.match(parcial.elRes.innerHTML, /HTTP 500/);
  console.log("Mapa: 7 cenarios de paginacao, cancelamento e erro passaram.");
}
main().catch(error => {console.error(error); process.exitCode = 1;});
