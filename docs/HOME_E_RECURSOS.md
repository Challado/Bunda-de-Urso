# Home na raiz do Radar Brasil

A home é o prefixo configurado em `web.url`, por exemplo
`https://servidor3.lucas.inf.br/openclaw/radar/`. Esse endereço serve `index.html`
na própria raiz, sem redirecionar para `resources/`.

```text
radar/
  index.html
  cadastro.html
  detalhe.html
  gestao.html
  usuarios.html
  status.html
  status-estado.html
  api.pse
  radar.conf
  dados/                    # privado, sem download HTTP
  resources/                # imagens, CSS, JavaScript e JSON públicos
```

O instalador publica as páginas na raiz, substitui a antiga pasta de recursos,
atualiza os links e aponta o descritor do projeto para a home. A checagem final
consulta a URL principal e exige a mesma página instalada. Os testes de
navegador abrem a home pelo prefixo do site e navegam até o cadastro.

## Altura adaptável do mapa

A home mede o espaço útil da tela, descontando cabeçalho, controles, legenda,
barra de status e rodapé. Usa a altura restante para mapa e resultados:

- Se a tabela couber, reduz o mapa e exibe os radares diretamente, sem rolagem
  da página.
- Se a tabela exigisse um mapa menor que o mínimo, mostra uma seção recolhível
  aberta por padrão, com rolagem dentro da lista. Recolher a lista amplia o mapa.
- Em telas muito baixas, permite a rolagem da página para manter controles e mapa
  legíveis. Redimensionamento, orientação e teclado virtual recalculam o layout.

Os limites ficam somente no `radar.conf`, também editáveis pela API do painel:

```ini
[interface]
mapa_min_percentual = 50
mapa_min_altura_px = 180
```

O percentual usa o espaço útil, não a altura total incluindo controles. O mínimo
em pixels evita um mapa ilegível. O painel aceita 10–90% e 120–600 pixels; o
instalador completa as opções ausentes sem sobrescrever as existentes.
`api.pse?rota=/api/v1/interface` publica somente esses dois números, sem abrir o
banco ou expor o restante da configuração. Se essa consulta falhar, a home usa
50% e 180 pixels. Imagens, CSS e JavaScript continuam em `resources/`.

## Configuração manual do servidor web

O nginx é administrado exclusivamente pelo operador. O instalador não muda
arquivos nem inicia/recarrega o serviço. A regra abaixo é uma referência para
aplicação manual nos dois `server` existentes. Substitui somente o bloco
`location /openclaw/radar/` que atualmente retorna 404 para tudo:

```nginx
location /openclaw/radar/ {
    index index.html;
    autoindex off;
    if ($uri !~ "^/openclaw/radar/(?:[A-Za-z0-9_-]+\\.html)?$") {
        return 404;
    }
    try_files $uri $uri/ =404;
}
```

Preserve o handler genérico `location ~ \.pse$` e o bloco específico de
`resources/`. O prefixo acima não usa `^~`: os scripts `.pse` continuam pelo
handler genérico, inclusive novos scripts. Páginas HTML da raiz são servidas;
configuração, banco, fila e código permanecem bloqueados, assim como a listagem
dos diretórios internos. Não troque esse bloco por uma liberação geral do site.

A regra foi exercitada com nginx temporário em `tests/test_home_nginx.py`, sem
alterar o nginx da produção. Aplique a regra manual primeiro, confira a sintaxe
e recarregue o serviço por sua conta. Depois atualize a aplicação como root:

```sh
cd /repositorios/git/Bunda-de-Urso-Dados &&
git pull --ff-only &&
bash instalar-servidor3.sh --conf /var/www/html/openclaw/radar/radar.conf --aplicar
```
