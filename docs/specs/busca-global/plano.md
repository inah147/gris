# Plano técnico — Busca global do Portal

> Requisitos e critérios de aceite: [spec.md](spec.md)

## 1. Visão geral

```
topbar (web_sidebar_base.html)
 ├─ botão "Buscar no portal…  Ctrl K"           ─┐
 └─ include portal_busca.html                    │ abre
     ├─ <dialog class="command-dialog">  ◄───────┘
     ├─ <script type="application/json">  ← busca_paginas (enrich_context)
     └─ portal_busca.js
          ├─ páginas + ações: filtro local a cada tecla
          └─ registros: GET /api/method/gris.api.busca_global.buscar (debounce 200 ms)
                          └─ fontes: associados, responsáveis, novos associados,
                                     projetos, captação, festas, transparência
```

## 2. Backend — `gris/api/busca_global.py`

### 2.1 Índice de páginas

`paginas_da_busca(sidebar_items, roles) -> list[dict]`

- Percorre a sidebar **já filtrada** por `build_sidebar()`; para o pai de cada grupo (índice
  do módulo) checa `user_has_access(path, roles=roles)` à parte, porque `_filter_items` mantém
  o pai quando algum filho é acessível.
- Acrescenta `PAGINAS_FORA_DO_MENU` (ex.: importar calendário). Só entra rota presente em
  `PAGE_ROLES`, e há teste travando isso (CA-S3).
- Junta sinônimos de `PALAVRAS_CHAVE` (ex.: `/administracao` → "configurações").
- Deduplica por URL (`/gestao_tarefas` é índice e também "Quadros").
- Saída: `{"titulo", "grupo", "url", "icone", "termos", "modulo": bool}`.

`enrich_context` grava em `context.busca_paginas` (só para sessão autenticada).

### 2.2 Endpoint de registros

```python
@frappe.whitelist(methods=["GET"])
def buscar(termo: str | None = None) -> dict
```

1. `_preparar_termo`: corta em 80 caracteres, quebra em até 5 palavras e escapa `%`, `_` e `\`
   do `LIKE`. Menos de 2 caracteres → `grupos: []`.
2. Para cada `Fonte` do registro `FONTES`: se `user_has_access(fonte.rota, roles=roles)`,
   chama `fonte.consultar(palavras)`. Uma `frappe.PermissionError` omite o grupo.
3. `_ranquear` ordena os candidatos (até 20 por fonte) por: título igual > começa com o termo >
   alguma palavra começa com a primeira palavra do termo > contém. Depois corta em 5.

Filtro comum (`_filtros_de_nome`): cada palavra vira `[campo, "like", "%palavra%"]` em AND,
o que dá CA-04.3. Com uma única palavra, campos secundários (ex.: `registro` do associado)
entram em `or_filters`.

| Fonte | Rota (gate) | Consulta | Observação |
|---|---|---|---|
| associados | `/associados/detalhe` | `get_list("Associado")` | contexto: ramo · status · registro |
| responsaveis | `/associados/responsavel` | `get_list("Responsavel")` | remove quem tem `associado` gravado ou `name` igual a um Associado (uma consulta agregada) |
| novos_associados | `/recepcao/ficha_registro` | `get_list("Novo Associado")` | contexto: ramo · status do funil |
| projetos | `/projetos/projeto` | `get_list("Projeto")` | |
| captacao | `/captacao/projeto` | `get_all` + filtro do kanban | mesma regra de `listar_kanban` |
| festas | `/festas/festa` | `get_list("Festa")` | contexto: data · status |
| transparencia | `/portal_transparencia` | `get_all` com `publicado = 1` | conteúdo público; ordena por `ano_referencia` (o campo com acento quebra o `order_by`) |

## 3. Frontend

### 3.1 Markup — `gris/templates/includes/portal_busca.html`

- `<dialog id="portal-busca" class="dialog command-dialog portal-busca">` com o painel
  `.command[data-command-initialized]` (impede o `command.js` de assumir o campo).
- `header` com lupa, `input[role=combobox]` e spinner; `div[role=menu]` para os resultados;
  `empty()` com `gris-search` (oculto); aviso de erro (oculto); rodapé com a legenda; botão
  fechar.
- `<script type="application/json" id="portal-busca-paginas">{{ busca_paginas | tojson }}</script>`.

### 3.2 Topbar — `web_sidebar_base.html` + `web_sidebar_base.css`

- O conteúdo da topbar vira três colunas em grid (`início | busca | ações`), o que centraliza a
  busca de verdade, independentemente do tamanho do breadcrumb e das ações.
- < 768 px: volta a flex, a busca vira botão de ícone ao lado das ações.

### 3.3 Controlador — `gris/public/js/portal_busca.js`

- Estado: `paginas`, `acoes`, `registros` (último resultado do servidor), `ativo`, `seq`.
- `input` → `renderizar()` imediato (páginas/ações) + `agendarBusca()` (debounce 200 ms,
  `AbortController` e número de sequência contra resposta fora de ordem).
- Enquanto a nova resposta não chega, os grupos de registro anteriores ficam na tela,
  esmaecidos (`aria-busy`), para a lista não "pular".
- `fetch` direto em `/api/method/...` (o `frappe.call` do portal não chama `error`).
- DOM montado com `createElement` + `textContent`; ícones pelo sprite local.
- Ações reutilizam os `data-action` que o shell já trata (`toggle-theme`, `logout`).

### 3.4 Estilo — `gris/public/css/portal_busca.css`

Só o que o `.command-dialog` não cobre: gatilho, linha de contexto do item, rodapé,
spinner, estado vazio compacto, ancoragem no topo em mobile e esconder o `::before`
"No results found" do Basecoat (o vazio é o mascote).

## 4. Tarefas

- [x] T1 — Spec e plano (este documento).
- [x] T2 — `busca_global.py`: índice de páginas, fontes, ranking, endpoint.
- [x] T3 — `enrich_context` → `context.busca_paginas`.
- [x] T4 — Include do diálogo, gatilho na topbar e versão de asset do shell.
- [x] T5 — `portal_busca.js` (filtro local, busca remota, teclado, ações).
- [x] T6 — `portal_busca.css` + ajuste do grid da topbar.
- [x] T7 — Testes de unidade (`gris/tests/test_busca_global.py`).
- [x] T8 — E2E Playwright (`gris/tests/e2e/test_busca_global.py`).
- [x] T9 — Lint (pre-commit + semgrep do Frappe).

## 5. Riscos

| Risco | Mitigação |
|---|---|
| `user_has_access` é *fail-open* para rota não mapeada | Índice extra só aceita rota de `PAGE_ROLES` (teste). Gates de fonte apontam para rotas mapeadas (teste). |
| `user_has_access` lê `form_dict["name"]` em `/associados/detalhe` | A permissão de DocType do `get_list` continua barrando quem não tem leitura de Associado. |
| Muitas consultas por tecla | Debounce, mínimo de 2 caracteres, limite 20 por fonte, cancelamento da requisição anterior. |
| `command.js` inicializando o mesmo painel | `data-command-initialized` no markup. |

## 6. Matriz de validação

| CA | Teste de unidade | E2E (Playwright) |
|---|---|---|
| CA-01.1 | — | gatilho visível e centralizado (desktop) |
| CA-01.2 | — | viewport 390 px: botão só com ícone, sem rolagem horizontal |
| CA-01.3 | `test_visitante_nao_busca` | página pública sem gatilho |
| CA-02.1/2/3 | — | clique, `Ctrl K`, `/`, `Esc`, reabrir vazio |
| CA-03.1 | `test_indice_*` | lista inicial com módulos e ações |
| CA-04.1 | — | "contribuicao" acha "Contribuições Mensais" sem requisição |
| CA-04.2 | `test_termo_curto_*` | requisição só com ≥ 2 caracteres; resposta antiga descartada |
| CA-04.3 | `test_palavras_em_qualquer_ordem` | — |
| CA-04.4/5 | `test_ranking_*`, `test_limite_por_grupo` | grupos e ordem na tela |
| CA-04.6 | — | termo sem resultado mostra o mascote |
| CA-04.7 | — | rota simulada com falha mostra o aviso |
| CA-05.x | — | setas, `Enter` navega, mouse destaca |
| CA-06.x | — | ação de tema alterna `html.dark` |
| CA-S1/S2 | `test_usuario_sem_papel_*` | usuário restrito não vê associados |
| CA-S3 | `test_paginas_extras_mapeadas`, `test_gates_mapeados` | — |
| CA-S4 | `test_endpoint_*` | — |
| CA-S5 | `test_subtitulo_sem_dado_sensivel` | — |
| CA-S6 | — | nome com `<img onerror>` aparece como texto |
| CA-P1 | `test_termo_*` | — |
| CA-D1/D2 | — | screenshots claro/escuro, desktop/mobile |

## 7. Como validar

```bash
# Unidade (26 testes)
bench --site dev.gris run-tests --app gris --module gris.tests.test_busca_global

# Ponta a ponta no site vivo (13 cenários; screenshots em gris/tests/e2e/shots/busca_global/)
cd /workspace/frappe-bench && env/bin/python apps/gris/gris/tests/e2e/test_busca_global.py
```
