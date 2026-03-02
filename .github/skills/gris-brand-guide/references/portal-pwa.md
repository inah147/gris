# Marca no Portal Web e PWA

## Portal Web

### Arquivos de referência
- `gris/templates/base.html`
- `gris/templates/portal_clean.html`
- `gris/templates/web_sidebar_base.html`

### Regras
1. Carregar e priorizar `design-system.css` e `components.css`.
2. Manter consistência de hierarquia visual entre desktop e mobile.
3. Em ajustes locais de página (`www/*`), evitar desviar de tokens canônicos.

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

## Anti-padrões
- Corrigir branding só no CSS e esquecer `manifest.json`/meta tags.
- Alterar assets PWA sem validar instalação e atualização do Service Worker.
