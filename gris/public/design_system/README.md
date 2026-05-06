# GRIS Design System (Basecoat)

Este diretorio contem a base do novo design system do projeto, com assets locais
instalados via npm (sem CDN), macros Jinja e icones Lucide locais.

## Estrutura

- `css/`: estilos basecoat locais e tema exportado do shadcn
- `js/`: scripts basecoat e inicializacao global
- `components/`: macros Jinja geradas pelo CLI e macros de composicao
- `icons/lucide/`: sprite local de icones
- `fonts/`: fontes locais usadas pelo tema
- `docs/`: catalogo de cobertura dos componentes

## Atualizacao de assets

No diretorio `apps/gris`:

```bash
npm run design-system:sync
```

Esse comando sincroniza:

1. CSS e JS do Basecoat para `gris/public/design_system`
2. Sprite local do Lucide para `gris/public/design_system/icons/lucide`
3. Fonte Figtree para `gris/public/design_system/fonts/figtree`

## Uso em templates

Os assets globais sao carregados em `gris/templates/base.html`.

Para macros Jinja:

```jinja
{% from "public/design_system/components/generated/dialog.html.jinja" import dialog %}
{% from "public/design_system/components/composed/basecoat-composed.html.jinja" import empty %}
```
