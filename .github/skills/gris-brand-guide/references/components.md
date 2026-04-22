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
- Gerados com JS local: `command`, `dialog`, `dropdown-menu`, `popover`, `select`, `sidebar`, `tabs`, `toast`.
- Compostos sem JS dedicado: `accordion`, `alert`, `avatar`, `badge`, `breadcrumb`, `button`, `button-group`, `card`, `checkbox`, `empty`, `field`, `form`, `input`, `input-group`, `item`, `kbd`, `label`, `pagination`, `progress`, `radio-group`, `skeleton`, `slider`, `spinner`, `switch`, `table`, `textarea`, `theme-switcher`, `tooltip`.
- Ícones: macro `lucide_icon` com sprite local em `/assets/gris/design_system/icons/lucide/sprite.svg`.

## Regras de implementação
- Botões devem usar macros/classes Basecoat (`button`, `btn-primary`, `btn-outline`, variantes de tamanho) antes de CSS local.
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
