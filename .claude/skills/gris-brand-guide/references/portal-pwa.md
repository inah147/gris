# Marca no Portal Web e PWA

## Portal Web

### Arquivos de referência
- `gris/templates/base.html`
- `gris/templates/web_sidebar_base.html`
- `gris/templates/portal_clean.html` (legado/fluxos sem shell)
- `gris/public/design_system/README.md`
- `gris/public/design_system/components/README.md`
- `gris/public/design_system/docs/components-catalog.md`

### Regras
1. Carregar e priorizar Basecoat por meio de `gris/templates/base.html`.
2. Manter consistência de hierarquia visual entre desktop e mobile.
3. Em ajustes locais de página (`www/*`), evitar desviar de tokens/macros Basecoat.
4. Em páginas autenticadas com navegação, preferir `templates/web_sidebar_base.html`.
5. Não carregar `/assets/gris/design_system/*` em Desk; esses assets são do Portal.

## PWA

### Arquivos de referência
- `gris/public/manifest.json`
- `gris/public/js/pwa-init.js`
- `gris/public/js/service-worker.js`
- `gris/public/images/icons/android/`
- `gris/public/images/icons/ios/`

### Regras de marca para PWA
1. `theme_color` e `meta theme-color` devem refletir decisão oficial de marca.
2. Ícones devem ser consistentes entre plataformas (Android/iOS).
3. Nome curto e descrição do app devem manter tom institucional do produto.
4. Toda alteração de ícone/manifest deve ser validada em tela inicial e splash.

## Responsividade
- A interface deve ser funcional e legível em mobile e desktop.
- Diferenças por dispositivo são permitidas quando melhoram usabilidade, sem quebrar identidade visual.
- Componentes Basecoat devem manter área de toque adequada, foco visível e layout estável em breakpoints menores.

## Compatibilidade legado
- `design-system.css`, `components.css`, `portal_clean.html` e `gris/public/components/` podem existir em páginas antigas.
- Em nova interface, usar Basecoat e macros Jinja como primeira opção.

## Anti-padrões
- Corrigir branding só no CSS e esquecer `manifest.json`/meta tags.
- Alterar assets PWA sem validar instalação e atualização do Service Worker.
- Criar novo CSS global de Portal quando a necessidade é local da rota.
- Misturar Basecoat com componentes nativos do Frappe Desk.
