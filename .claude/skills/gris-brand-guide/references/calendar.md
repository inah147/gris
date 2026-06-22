# Componente `calendar` — design system Basecoat

Calendário reutilizável do Portal GRIS com três modos: **Mês**, **Semana** (com ou sem eixo de horas) e **Lista**. O modo **Lista** possui duas variantes secundárias: **Normal** e **Por categoria**; ambas podem mostrar apenas dias com evento ou todos os dias de um intervalo explícito. O componente implementa toolbar com seletor de modo, navegação prev/hoje/next, controles da lista, filtros por categoria e dispatch de cliques via `CustomEvent` — **não** implementa o handler do clique; cada página decide o comportamento.

## Quando usar
- Visualização de eventos por mês/semana/lista em qualquer página de Portal.
- Substitui implementações ad-hoc de tabelas de calendário (ex.: agenda_visitas anterior).

## Quando NÃO usar
- Em telas Desk: o componente não pertence ao Desk e não deve ser carregado lá.
- Quando o requisito for um seletor de data (use `datepicker` em vez disso).
- Quando o requisito for matriz `dia × categoria` fora do modo Lista. Em Mês/Semana as categorias continuam sendo modeladas como cores + filtros; somente a variante `Lista por categoria` cria colunas alinhadas por categoria.

## Paths canônicos
- Macro: `gris/public/design_system/components/generated/calendar.html.jinja`
- JS: `gris/public/design_system/js/components/calendar.js`
- CSS: `gris/public/design_system/css/calendar.css`
- Catálogo: `gris/public/design_system/docs/components-catalog.md`

Os três assets são carregados automaticamente via `gris/templates/base.html` (versionados por `design_system_asset_version`).

## Assinatura do macro

```jinja
{% from "public/design_system/components/generated/calendar.html.jinja" import calendar %}

{{ calendar(
    id=None,
    events=[],
    categories=[],
    initial_mode="month",
    initial_date=None,
    initial_list_variant="default",
    allowed_modes=["month", "week", "list"],
    week_show_hours=True,
    list_show_all_days=False,
    list_range_start=None,
    list_range_end=None,
    hour_range=[0, 24],
    first_weekday=0,
    locale="pt-BR",
    filters_enabled=True,
    show_toggle=True,
    empty_message="Nenhum evento.",
    attrs={}
) }}
```

| Param | Tipo | Default | Propósito |
|---|---|---|---|
| `id` | string | auto | id único do elemento root |
| `events` | list[dict] | `[]` | lista plana de eventos (ver schema abaixo) |
| `categories` | list[dict] | `[]` | categorias de cor + filtros (ver schema) |
| `initial_mode` | `"month"` \| `"week"` \| `"list"` | `"month"` | modo inicial; em mobile e quando omitido pela página, o JS força `"list"` |
| `initial_date` | string ISO `YYYY-MM-DD` | `today` | data âncora do calendário |
| `initial_list_variant` | `"default"` \| `"category"` | `"default"` | variante secundária do modo Lista |
| `allowed_modes` | list | os 3 modos | subset do toggle |
| `week_show_hours` | bool | `True` | habilita o eixo de horas no modo Semana e expõe o checkbox "Mostrar horários" |
| `list_show_all_days` | bool | `False` | no modo Lista, mostra todos os dias do intervalo em vez de apenas os dias com evento |
| `list_range_start` | string ISO `YYYY-MM-DD` | início do mês âncora | início explícito do intervalo da Lista |
| `list_range_end` | string ISO `YYYY-MM-DD` | fim do mês âncora | fim explícito do intervalo da Lista |
| `hour_range` | `[int,int]` | `[0,24]` | janela de horas exibida no modo Semana com horário |
| `first_weekday` | int | `0` | 0 = segunda, 6 = domingo |
| `locale` | string | `"pt-BR"` | usado por `Intl.DateTimeFormat` para labels |
| `filters_enabled` | bool | `True` | mostra/oculta o popover de filtros |
| `show_toggle` | bool | `True` | mostra/oculta o segmented control de modos |
| `empty_message` | string | `"Nenhum evento."` | texto do modo Lista quando filtrado vazio |
| `attrs` | dict | `{}` | atributos extras no root (`class`, `data-*`) |

## Contrato de dados

### Evento

```python
{
    "id": str,                # obrigatório, único
    "title": str,             # obrigatório
    "start": str,             # ISO 8601: "YYYY-MM-DD" ou "YYYY-MM-DDTHH:MM:SS"
    "end": str | None,        # opcional; mesmo formato
    "all_day": bool,          # default True quando start não tem hora
    "category": str | None,   # casa com categories[].name
    "color": str | None,      # opcional; sobrepõe a cor da categoria
    "icon": str | None,       # opcional; nome do ícone Lucide a renderizar antes do título
    "icon_color": str | None, # opcional; cor do ícone (token CSS ou hex). Default = cor da categoria
    "data": dict,             # payload livre, repassado em event-click.detail
}
```

Eventos sem `category` aparecem sempre (não filtráveis pelo popover).

`icon` aceita qualquer nome do sprite local em `/assets/gris/design_system/icons/lucide/sprite.svg`. Use para sinalizar status (ex.: confirmado, pendente, atrasado). Não use para personalizar excessivamente — o componente é genérico.

### Categoria

```python
{ "name": "Filhotes", "label": "Filhotes", "color": "var(--info)" }
```

`color` aceita token CSS (`var(--info)`) ou hex (`#3b82f6`). `label` separado de `name` permite que `name` seja uma chave técnica e `label` seja o texto exibido.

## Eventos disparados (no elemento root)

```js
const cal = document.getElementById("agenda-visitas-calendar");

cal.addEventListener("gris:calendar:event-click", (event) => {
    const { id, title, start, end, all_day, category, data } = event.detail;
    // a página decide o que fazer aqui (abrir modal, navegar, etc.)
});
```

O componente **não** dispara nenhum outro evento. Hover, double-click e drag NÃO são suportados.

## API JavaScript pública

A inicialização registra a API no próprio elemento root:

```js
const cal = document.getElementById("agenda-visitas-calendar");

cal.events = [...];           // setter: re-renderiza imediatamente
cal.activeCategories = [...]; // setter: sincroniza filtros/categorias ativas
cal.setMode("week");          // troca o modo
cal.setListVariant("category");
cal.setListShowAllDays(true);
cal.setListRange("2026-01-01", "2026-12-31");
cal.setActiveCategories(["Lobinho", "Escoteiro"]);
cal.goToDate("2026-05-01");   // muda a data âncora
cal.refresh();                // re-renderiza com state atual
```

`cal.events` (getter) devolve a lista bruta no formato passado pelo backend.

Use `cal.events = updated` após mutação local (ex.: confirmar/cancelar visita) para evitar reload da página.

## Comportamento por modo

### Mês
- Grid 7×6, dias do mês corrente; dias adjacentes ficam em cinza claro.
- Eventos multi-dia são desenhados como barras absolutas sobre a semana; modificadores `--continued-left` / `--continued-right` indicam continuidade entre semanas.
- Quando os eventos excedem o limite visível por célula (3 lanes desktop, 2 mobile), aparece um indicador estático `+N` na célula. **Não há popover, não há ação no `+N`** — é apenas informativo.

### Semana sem horário
- 7 colunas; eventos empilhados verticalmente em cada coluna.
- Cards mostram título e horário (se houver).

### Semana com horário
- 7 colunas + eixo Y de horas (intervalo configurável via `hour_range`).
- Eventos com hora ficam posicionados absolutamente dentro da coluna do dia.
- Sobreposições são tratadas com algoritmo de **lanes**: cada conjunto de eventos sobrepostos divide a largura da coluna em N partes iguais.
- Eventos `all_day` (ou sem horário) aparecem em uma faixa "Dia inteiro" no topo de cada coluna do dia.
- **Limitação**: eventos que cruzam meia-noite são fatiados visualmente em duas peças (uma em cada dia).

### Lista
- A variante **Normal** mostra a lista tradicional: data à esquerda, eventos à direita, agrupados por mês.
- A variante **Por categoria** cria colunas alinhadas pela mesma linha de data; em mobile, essas colunas empilham mantendo o rótulo da categoria em cada bloco.
- Eventos multi-dia aparecem em todos os dias que cobrem.
- O componente pode limitar a lista a um intervalo explícito (`list_range_start` / `list_range_end`); sem isso, usa o mês da data âncora.
- O checkbox `Mostrar todos os dias` alterna entre renderizar apenas dias com evento ou todos os dias do intervalo.
- O toggle prev/hoje/next fica oculto neste modo (a navegação se dá por scroll e por alteração do intervalo/âncora pela página).

## Toolbar embutida

```
[ Mês | Semana | Lista ]   [ < ] [ Hoje ] [ > ]   [ Normal | Por categoria ] [☑ Mostrar todos os dias] [ Filtros ▾ ]
                                                  (Semana: ☑ Mostrar horários)
```

- Toggle de modo é um `radiogroup` ARIA; `show_toggle=False` o oculta para forçar modo único.
- Em modo Lista, aparece um segundo `radiogroup` para a variante `Normal` / `Por categoria` e um checkbox para `Mostrar todos os dias`.
- Filtros: popover com checkbox por categoria, swatch da cor e botões "Todos"/"Nenhum".
- Em modo Semana, o checkbox "Mostrar horários" alterna `week_show_hours` em runtime.

## Acessibilidade

- Root: `role="application"` + `aria-label="Calendário"`.
- Modo Mês/Semana: container com `role="grid"`, células com `role="gridcell"` e `aria-label` legível.
- Modo Lista: estrutura semântica simples.
- Cards: `role="button"`, `tabindex="0"`; `Enter` e `Space` ativam o click.
- Toggle: `role="radiogroup"`.
- Focus ring usa `outline: 2px solid var(--ring)` (padrão Basecoat).

## Tokens utilizados

Cards usam estilo **pill tintada** derivado da cor da categoria (`--cal-cat-color`):

```css
--_color:    var(--cal-cat-color, var(--primary));            /* base saturada (borda + texto + ícone) */
--_bg:       color-mix(in srgb, var(--_color) 18%, white);    /* fundo pastel (mix sRGB) */
--_bg-hover: color-mix(in srgb, var(--_color) 28%, white);    /* hover ligeiramente mais saturado */
```

A borda usa `var(--_color)`, fundo `var(--_bg)`, texto e ícone também usam `var(--_color)`. Em dark mode, o fundo é re-derivado misturando com `black` (22% / 32%) para preservar contraste. Sem categoria, `--cal-cat-color` cai em `var(--primary)`.

**Arredondamento**: todas as superfícies retangulares (event-card, list-event, popovers, mode-toggle, body) usam `var(--radius-md)` para alinhar com o sistema (botões e popovers do Basecoat). Os modificadores `--continued-left`/`--continued-right` zeram o lado da continuação para barras multi-dia emendarem visualmente. Indicadores circulares decorativos (badge do "hoje", swatch de cor de filtro) seguem como `999px`.

No modo Lista, além da borda fina colorida em volta, o item ganha uma faixa lateral esquerda de 4px (`border-left: 4px solid var(--_color)`) para destacar a categoria em uma área de leitura maior.

> Por que sRGB e não oklch? oklch preserva luminância perceptual, o que para a faixa Tailwind 100-200 produz cores excessivamente desbotadas. sRGB mantém mais saturação visível na pastel.

Demais tokens: `--card`, `--foreground`, `--muted`, `--muted-foreground`, `--border`, `--ring`, `--accent`, `--primary`, `--primary-foreground`, `--warning`, `--destructive`, `--info`, `--success`, `--radius-sm`, `--radius-md`.

## Responsividade

- Desktop: layout completo, 3 lanes visíveis no Mês.
- Mobile (< 640px): grid Mês/Semana ganha scroll horizontal (largura mínima 560px); apenas 2 lanes visíveis no Mês; densidade de horas dobra (`--cal-px-per-min: 1.6`).
- Smart default: se a página não definir `initial_mode`, o JS escolhe `"list"` em mobile.

## Exemplo mínimo

```python
# rota.py
def get_context(context):
    context.events = [
        {
            "id": "evt-1",
            "title": "Reunião",
            "start": "2026-04-29T10:00:00",
            "end":   "2026-04-29T11:00:00",
            "all_day": False,
            "category": "Trabalho",
            "data": {"sala": "B-203"},
        },
    ]
    context.categories = [
        {"name": "Trabalho", "label": "Trabalho", "color": "var(--info)"},
    ]
```

```jinja
{# rota.html #}
{% from "public/design_system/components/generated/calendar.html.jinja" import calendar %}

{{ calendar(
    id="meu-calendario",
    events=events,
    categories=categories,
    initial_mode="week"
) }}
```

```js
// rota.js
document.getElementById("meu-calendario").addEventListener(
  "gris:calendar:event-click",
  (e) => {
    const { id, data } = e.detail;
    abrirModalDoEvento(id, data);
  }
);
```

## Anti-padrões

- Implementar handlers de click dentro do macro/JS do calendário (quebra reuso).
- Usar `<select>` nativo ou tabela HTML para imitar o mesmo comportamento em outra página.
- Renderizar HTML do `title` (o componente escapa o texto; use o `data` para pintura adicional na página).
- Usar `cal.refresh()` em vez de `cal.events = lista` quando os eventos mudam — o setter é a forma oficial.
- Cores hard-coded fora dos tokens shadcn (use `var(--info)`, `var(--success)`, etc.).
- Forçar reload da página após cada ação quando o estado pode ser atualizado via `cal.events`.
