# Componentes e padrões de UI

## Fontes canônicas
- `gris/public/design_system/components/README.md`
- `gris/public/design_system/docs/components-catalog.md`
- `gris/public/design_system/components/generated/`
- `gris/public/design_system/components/composed/basecoat-composed.html.jinja`
- `gris/public/design_system/components/composed/lucide.html.jinja`

## Princípios
1. Reusar antes de criar.
2. Compor com macros e tokens Basecoat.
3. Garantir estados visuais completos: default, hover, focus, active, disabled.
4. Isolar Portal e Desk quando houver conflito de componentes.

## Componentes prioritários
- Gerados com JS local: `calendar`, `command`, `datepicker`, `dialog`, `dropdown-menu`, `phone-input`, `popover`, `select`, `sidebar`, `tabs`, `toast`.
- Compostos sem JS dedicado: `accordion`, `alert`, `avatar`, `badge`, `breadcrumb`, `button`, `button-group`, `card`, `checkbox`, `empty`, `field`, `form`, `input`, `input-group`, `item`, `kbd`, `label`, `pagination`, `progress`, `radio-group`, `skeleton`, `slider`, `spinner`, `switch`, `table`, `textarea`, `theme-switcher`, `tooltip`.
- Ícones: macro `lucide_icon` com sprite local em `/assets/gris/design_system/icons/lucide/sprite.svg`.

## Componente `empty`

Macro composta em `public/design_system/components/composed/basecoat-composed.html.jinja`. CSS de extensão em `public/design_system/css/empty.css` (carregado em `templates/base.html`).

### Assinatura

```jinja
{{ empty(
    title,                    # obrigatório — texto principal (vai em <h2>)
    description=None,         # subtítulo opcional
    icon=None,                # HTML do ícone (use `lucide_icon(...)`) — variante simples
    image=None,               # caminho de imagem — variante com imagem (precede icon)
    image_size="md",          # "sm" | "md" | "lg" | qualquer max-width CSS (ex.: "200px")
    image_alt="",             # alt da imagem; preferir descrição curta em PT-BR
    primary_action=None,      # dict {label, href?, onclick?, attrs?} — btn-primary
    secondary_action=None,    # idem — btn-outline
    ghost_action=None,        # idem — btn-ghost
    action=None,              # slot HTML livre (legado, evitar em novos usos)
    attrs={}                  # atributos extras na <section>
) }}
```

Cada `*_action` é um dict com:
- `label` (obrigatório, string)
- `href` (opcional — se setado, vira `<a>`; senão `<button type="button">`)
- `onclick` (opcional, string JS)
- `attrs` (opcional, dict para `id`, `data-*`, `class` extra etc.)

### Variantes

- **Simples (ícone)** — passar `icon=lucide_icon(...)`. Use quando o estado vazio for utilitário (filtro sem resultado, lista pequena).
- **Simples com imagem** — passar `image="/assets/gris/images/gris-character/<arquivo>.png"` e `image_size`. Use para empty states de alta visibilidade (página principal, primeira vez, erro amigável).

`image` precede `icon` quando ambos são passados.

### Imagens recomendadas (mascote Gris)

Disponíveis em `gris/public/images/gris-character/` — sirva via `/assets/gris/images/gris-character/<arquivo>`:

- `gris-search.png` — busca/sem resultado de filtro
- `gris-confused.png` — erro genérico, dúvida
- `gris-idea.png` / `gris-idea-stand-up.png` — sugestão/dica
- `gris-idle.png` — estado neutro/aguardando ação
- `gris-cientist.png` — análise, dados, relatórios
- `gris-police.png` — bloqueio, sem permissão
- `gris-ramo-filhotes.png` / `gris-ramo-filhotes-sentado.png` — gestão de adultos/crianças, acolhimento

### Regra mandatória de uso

Antes de aplicar o macro `empty` em uma nova superfície, **perguntar ao usuário qual versão usar** (simples com ícone vs. simples com imagem). Se a escolha for imagem, **sugerir um dos arquivos disponíveis em `public/images/gris-character/`** com base no contexto do empty (lista da seção acima).

Não usar imagens externas aleatórias, fotos ou SVGs avulsos para empty state — o mascote Gris é o padrão de marca para essa variante.

### Tamanhos

`image_size`:
- `"sm"` (96px) — empty inline em card pequeno;
- `"md"` (160px, default) — empty padrão de página/seção;
- `"lg"` (240px) — empty de página inteira (rota dedicada);
- string CSS livre (`"180px"`, `"12rem"`) — ajuste pontual via `max-width` inline.

### Acessibilidade

- `image_alt` em PT-BR descritivo quando a imagem agregar contexto; vazio só quando 100% decorativa.
- Texto principal vai em `<h2>` — garantir hierarquia correta na página.
- Botões usam classes canônicas (`btn-primary`, `btn-outline`, `btn-ghost`); para tamanho compacto, passe `attrs={"class": "btn-sm-primary"}` etc., conforme regra geral de `btn-sm-<variant>`.

### Exemplo — variante imagem com ações

```jinja
{{ empty(
    title="Nenhum projeto ainda",
    description="Crie seu primeiro projeto para começar.",
    image="/assets/gris/images/gris-character/gris-idea.png",
    image_size="md",
    image_alt="Gris com lâmpada acesa indicando ideia",
    primary_action={"label": "Criar projeto", "href": "/projetos/novo"},
    secondary_action={"label": "Importar", "onclick": "abrirImport()"},
    ghost_action={"label": "Saiba mais", "href": "/ajuda/projetos"}
) }}
```

### Exemplo — variante ícone

```jinja
{{ empty(
    title="Nenhum resultado",
    description="Tente ajustar os filtros acima.",
    icon=lucide_icon("search-x", size="md")
) }}
```

## Visualizações de calendário
Para qualquer página que precise renderizar eventos por mês, semana ou lista, usar o componente `calendar` (`gris/public/design_system/components/generated/calendar.html.jinja`). Detalhes de contrato, eventos disparados e API JS em `references/calendar.md`. **Não** implementar tabela ou matriz custom para calendários — categorias devem virar cores + filtros do componente em vez de colunas paralelas.

## Regras de implementação
- Botões devem usar macros/classes Basecoat (`button`, `btn-primary`, `btn-outline`, variantes de tamanho) antes de CSS local.
- Para botões em tamanho `sm`, use sempre a classe combinada `btn-sm-<variant>` (ex.: `btn-sm-outline`, `btn-sm-primary`, `btn-sm-destructive`, `btn-sm-ghost`). **Nunca** componha `btn-outline btn-sm` / `btn-primary btn-sm` — a forma decomposta não é estilizada pelo bundle Basecoat e quebra o visual.
- Para selecionar datas em páginas de Portal, use sempre a macro `datepicker` (`public/design_system/components/generated/datepicker.html.jinja`). `<input type="date">` é proibido no Portal porque não respeita o tema shadcn nem o padrão visual dos demais campos. Use `mode="single"` para data única e `mode="range"` para intervalos (`name_start`/`name_end`).
- Formulários devem usar `field`, `form`, `input`, `textarea`, `select`, `checkbox`, `radio_group` e `switch` quando aplicável.
- Cards, badges, tabelas, estados vazios e feedback devem vir das macros compostas.
- Evitar criar “variante local” sem necessidade de negócio clara.
- Componentes de Portal devem viver em templates/assets de Portal; não adaptar componentes Desk para páginas `www` nem carregar Basecoat no Desk.

## Legado
`gris/public/css/components.css` e `gris/public/components/` são compatibilidade para telas existentes. Use apenas em manutenção de página legada ou quando ainda não existir equivalente Basecoat.

## Estados e feedback
- Loading: indicar ação em andamento sem bloquear leitura.
- Erro: usar cor semântica + mensagem clara e orientada à ação.
- Sucesso: curto, objetivo e com próximo passo quando relevante.

## Anti-padrões
- Componente novo sem inventário prévio do catálogo Basecoat.
- CSS inline para estado visual recorrente.
- Estado de foco invisível.
- Misturar classes Basecoat com componentes nativos do Frappe Desk.
- Compor `btn-<variant>` com `btn-sm` em vez de usar `btn-sm-<variant>`.
- Usar `<input type="date">` em páginas de Portal em vez da macro `datepicker`.
