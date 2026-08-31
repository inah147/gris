# Basecoat Components Catalog

## Convenções obrigatórias

### Classes de botão

Para tamanho `sm` use a classe combinada (`btn-sm-<variant>`), nunca a forma decomposta `btn-<variant> btn-sm`.

- ✅ `btn-sm-outline`, `btn-sm-primary`, `btn-sm-destructive`, `btn-sm-ghost`
- ❌ `btn-outline btn-sm`, `btn-primary btn-sm`

A forma decomposta não é estilizada pelo bundle do Basecoat usado pelo Gris e produz botões sem visual correto. Quando precisar de tamanho `sm`, use sempre a classe combinada (vale para botões em paginações, ações de tabela, dialogs e toolbars).

### Seleção de datas

Páginas de Portal **não devem** usar `<input type="date">`. O input nativo não respeita o tema shadcn, varia entre navegadores e quebra a consistência visual com os demais campos.

Toda seleção de data em páginas de Portal deve usar a macro `datepicker` do design system (`public/design_system/components/generated/datepicker.html.jinja`):

```jinja
{% from "public/design_system/components/generated/datepicker.html.jinja" import datepicker %}

{{ datepicker(name="data_inicio", value=(filtros.data_inicio or '')) }}
{{ datepicker(name="periodo", mode="range") }}
```

Use `mode="single"` para data simples e `mode="range"` quando o filtro precisar de início e fim (gera `name_start` e `name_end` em hidden inputs).

## Componentes gerados via CLI (macro + JS local)

- calendar
- command
- datepicker
- dropdown-menu
- phone-input
- popover
- select
- sidebar
- tabs
- toast

### calendar

Macro: `public/design_system/components/generated/calendar.html.jinja`.
Comportamento: `public/design_system/js/components/calendar.js`. CSS: `public/design_system/css/calendar.css`.

Calendário reutilizável com três modos (Mês, Semana, Lista). No modo Semana é possível mostrar/ocultar o eixo de horas; eventos sem horário aparecem em uma faixa "Dia inteiro" no topo de cada coluna. Eventos sobrepostos no modo Semana com horário são distribuídos em "lanes" lado a lado dentro da coluna do dia. No modo Mês, eventos multi-dia são desenhados como barras absolutas posicionadas sobre a semana; quando excedem o espaço do dia, surge um indicador estático `+N` na célula. O modo Lista ganhou duas variantes secundárias: `Normal` e `Por categoria`; ambas podem renderizar apenas os dias com evento ou todos os dias de um intervalo explícito. Categorias viram cores (e filtros opcionais via popover na toolbar). Cliques em cards são repassados para a página via `CustomEvent("gris:calendar:event-click")`; o componente NÃO implementa nenhum handler de clique.

API:

```jinja
{% from "public/design_system/components/generated/calendar.html.jinja" import calendar %}

{{ calendar(
    id=None,
    events=[],                               # ver schema abaixo
    categories=[],                           # ver schema abaixo
    initial_mode="month",                    # "month" | "week" | "list"
    initial_date=None,                       # "YYYY-MM-DD"; default = hoje
    initial_list_variant="default",         # "default" | "category"
    allowed_modes=["month", "week", "list"],
    week_show_hours=True,
    list_show_all_days=False,
    list_range_start=None,                   # "YYYY-MM-DD"; default = início do mês âncora
    list_range_end=None,                     # "YYYY-MM-DD"; default = fim do mês âncora
    hour_range=[0, 24],
    first_weekday=0,                         # 0 = segunda, 6 = domingo
    locale="pt-BR",
    filters_enabled=True,
    show_toggle=True,
    empty_message="Nenhum evento.",
    attrs={}
) }}
```

Schema de evento:

```python
{
    "id": str,                # obrigatório, único
    "title": str,             # obrigatório
    "start": str,             # ISO 8601 ("YYYY-MM-DD" ou "YYYY-MM-DDTHH:MM:SS")
    "end": str | None,        # opcional, mesmo formato
    "all_day": bool,          # default True quando start não tem hora
    "category": str | None,   # casa com categories[].name
    "color": str | None,      # opcional; sobrepõe a cor da categoria (token CSS ou hex)
    "icon": str | None,       # opcional; nome do ícone Lucide a renderizar antes do título
    "icon_color": str | None, # opcional; cor do ícone (default = cor da categoria)
    "data": dict,             # payload livre, repassado em event-click.detail
}
```

Schema de categoria:

```python
{ "name": "Filhotes", "label": "Filhotes", "color": "var(--info)" }
```

Eventos: `gris:calendar:event-click` no elemento raiz, com `detail = { id, title, start, end, all_day, category, data }`.
API pública via DOM: `el.events` (getter/setter — re-renderiza ao setar), `el.activeCategories` (getter/setter), `el.setMode(mode)`, `el.setListVariant("default" | "category")`, `el.setListShowAllDays(bool)`, `el.setListRange(startIso, endIso)`, `el.setActiveCategories(names)`, `el.goToDate(iso)`, `el.refresh()`.

Em mobile (viewport < 640px), se a página não passar `initial_mode`, o componente assume `"list"` como default; o usuário pode trocar pelo toggle.

### phone-input

Macro: `public/design_system/components/generated/phone-input.html.jinja`.
Comportamento: `public/design_system/js/components/phone-input.js`. CSS: `public/design_system/css/phone-input.css`.

Compõe um seletor de país (combobox interno via `select`) e um campo de número, num único `input-group`. O componente combina o DDI selecionado com os dígitos digitados em um `<input type="hidden">` no formato `+{ddi}{digits}`. Para Brasil aplica a máscara `(XX) X XXXX-XXXX`; para os demais países deixa apenas dígitos.

API:

```jinja
{{ phone_input(
    id=None,
    name=None,                     # nome do hidden input com o valor completo (+5511...)
    value=None,                    # valor inicial completo (resolve país pelo prefixo)
    default_country="BR",          # ISO 3166-1 alpha-2 quando value é vazio
    placeholder="Número de telefone",
    search_placeholder="Buscar país...",
    countries=None,                # lista [{iso, name, dial, flag}]; default = get_phone_countries()
    attrs={},
    input_attrs={}
) }}
```

A lista padrão vem do helper `gris.utils.phone_countries.get_phone_countries`, exposto como global do Jinja em `hooks.py`.

Eventos: `phone-input:change` no elemento raiz com `detail = { value, dial, digits, iso }`.
API pública via DOM: `el.value` (getter/setter — formato `+5511...`).

### datepicker

Macro: `public/design_system/components/generated/datepicker.html.jinja`.
Comportamento: `public/design_system/js/components/datepicker.js`. CSS: `public/design_system/css/datepicker.css`.

API:

```jinja
{{ datepicker(
    id=None,
    name=None,                  # hidden input (single) ou prefixo (range -> name_start, name_end)
    mode="single",              # "single" | "range"
    value=None,                 # ISO "YYYY-MM-DD" ou {"start": "...", "end": "..."}
    min=None, max=None,         # ISO "YYYY-MM-DD"
    placeholder="Selecione uma data",
    locale="pt-BR",
    main_attrs={}, trigger_attrs={}
) }}
```

Exemplos:

```jinja
{# Data simples #}
{{ datepicker(name="data_nascimento", mode="single", max=today_iso) }}

{# Intervalo #}
{{ datepicker(name="periodo", mode="range", min="2026-01-01") }}
```

Eventos: `datepicker:change` no elemento raiz com `detail.value` (string ISO no `single`, `{start, end}` no `range`).
API pública via DOM: `el.value` (getter/setter), `el.open()`, `el.close()`.

Cabeçalho do popover: duas linhas, cada uma com suas setas `‹ ›`. Em cima o **ano** (as setas andam de ano em ano; clicar no número abre a lista de anos); embaixo o **mês** (setas de mês em mês). Na lista de anos, as setas do ano passam a paginar de 12 em 12 e escolher um ano apenas troca o ano do calendário — o popover continua aberto, no mesmo mês, e volta para a grade de dias. `min`/`max` desabilitam anos cujo período inteiro está fora do intervalo. Datas distantes (nascimento, por exemplo) não exigem navegar mês a mês.

Quem monta o markup do datepicker fora da macro (kanban de tarefas, cadastro de projeto) precisa reproduzir as duas linhas do cabeçalho: `data-datepicker-year-toggle`, `data-datepicker-year-label`, `data-datepicker-year-prev/next` e `data-datepicker-month-row`.

Visual: o gatilho do datepicker tem borda padrão `1px solid var(--color-input)` e radius `--radius-md`, alinhada com `<input>` e `<select>` adjacentes em formulários. Foco e estado expandido usam `--color-ring` (borda + outline).

### table

Macro: `public/design_system/components/composed/basecoat-composed.html.jinja`.
Comportamento de ordenação: `public/design_system/js/components/table.js`. CSS de extensão: `public/design_system/css/table.css`.

Por padrão, a tabela é ordenável ao clicar no cabeçalho (`<th>`). Cada `<th>` ordenável vira um `<button>` que cicla entre `none → ascending → descending → none` (o estado `none` restaura a ordem original). O ícone (Lucide `chevrons-up-down` / `chevron-up` / `chevron-down`) reflete o estado.

API:

```jinja
{{ table(
    headers=[],          # lista de strings (HTML aceito via `safe`)
    rows=[],             # lista de listas (HTML aceito por célula)
    striped=false,       # zebra
    sortable=true,       # ordenar ao clicar nos cabeçalhos
    sort_skip=[],        # índices de colunas que NÃO devem ser ordenáveis
    attrs={}             # atributos extras na <table>
) }}
```

Exemplos:

```jinja
{# Coluna 0 (status visual) e coluna 7 (ações) não devem ser ordenáveis #}
{{ table(headers=hdrs, rows=[], sort_skip=[0, 7], attrs={"id": "minhaTabela"}) }}

{# Tabela com paginação server-side: desligar ordenação client-side #}
{{ table(headers=hdrs, rows=linhas, sortable=false) }}
```

Detecção de tipo: o JS inspeciona os valores da coluna e infere `number`, `date` (ISO `YYYY-MM-DD` ou `DD/MM/YYYY`) ou `text` (Intl.Collator `pt-BR`). Para forçar o tipo, definir `data-sort-type="number|date|text"` no `<th>`. Para casos onde o texto exibido difere do valor a ordenar (ex.: NPS com `<span>` decorativo), use `data-sort-value="..."` na `<td>`.

Eventos: `table:sort` no elemento da tabela, `detail = { columnIndex, direction }` (`direction ∈ "ascending" | "descending" | "none"`).

Quando desativar: tabelas com paginação ou ordenação server-side devem passar `sortable=false` para evitar ordenar apenas a página visível.

## Componentes com macro local sem JS dedicado

- dialog
- alert-dialog (composicao com dialog)
- combobox (composicao com select)

## Componentes de composicao (macro local)

- accordion
- alert
- avatar
- badge
- breadcrumb
- button
- button-group
- card
- checkbox
- empty
- field
- file-upload
- form
- input
- input-group
- item
- kbd
- label
- pagination
- progress
- radio-group
- skeleton
- slider
- spinner
- switch
- textarea
- theme-switcher
- tooltip

### empty

Macro: `public/design_system/components/composed/basecoat-composed.html.jinja`. CSS de extensão: `public/design_system/css/empty.css` (carregado via `templates/base.html`).

Componente para estados vazios (lista sem registros, filtro sem resultado, primeira vez). Suporta duas variantes mutuamente exclusivas via mídia: ícone Lucide ou imagem (mascote Gris). Aceita até três ações opcionais (primary, secondary outline, ghost). Conteúdo é centralizado vertical e horizontalmente.

API:

```jinja
{% from "public/design_system/components/composed/basecoat-composed.html.jinja" import empty %}
{% from "public/design_system/components/composed/lucide.html.jinja" import lucide_icon %}

{{ empty(
    title,                    # obrigatório
    description=None,         # subtítulo opcional
    icon=None,                # HTML do ícone — variante simples
    image=None,               # caminho de imagem — variante imagem (precede icon)
    image_size="md",          # "sm" (96px) | "md" (160px) | "lg" (240px) | string CSS livre
    image_alt="",             # alt em PT-BR
    primary_action=None,      # dict {label, href?, onclick?, attrs?} — btn-primary
    secondary_action=None,    # idem — btn-outline
    ghost_action=None,        # idem — btn-ghost
    action=None,              # slot HTML livre (legado)
    attrs={}
) }}
```

Variante ícone:

```jinja
{{ empty(
    title="Nenhum resultado",
    description="Tente ajustar os filtros acima.",
    icon=lucide_icon("search-x", size="md")
) }}
```

Variante imagem (mascote Gris):

```jinja
{{ empty(
    title="Nenhum projeto ainda",
    description="Crie seu primeiro projeto para começar.",
    image="/assets/gris/images/gris-character/gris-idea.png",
    image_size="md",
    image_alt="Gris com lâmpada acesa indicando ideia",
    primary_action={"label": "Criar projeto", "href": "/projetos/novo"}
) }}
```

Imagens disponíveis em `public/images/gris-character/` (servidas em `/assets/gris/images/gris-character/`): `gris-search`, `gris-confused`, `gris-idea`, `gris-idea-stand-up`, `gris-idle`, `gris-cientist`, `gris-police`, `gris-ramo-filhotes`, `gris-ramo-filhotes-sentado`. A escolha entre variante ícone vs. imagem deve ser confirmada com o usuário antes da implementação (ver `gris-brand-guide/references/components.md`, seção "Componente `empty`").
