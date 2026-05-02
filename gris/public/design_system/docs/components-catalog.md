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
- table
- textarea
- theme-switcher
- tooltip
