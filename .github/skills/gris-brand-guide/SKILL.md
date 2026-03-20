---
name: gris-brand-guide
description: Define e aplica o guia de marca do GRIS para Portal Web e PWA, cobrindo tokens visuais (cores, tipografia, espaçamento, radius, sombras), componentes reutilizáveis, responsividade, acessibilidade e microcopy PT-BR. Use esta skill sempre que o pedido envolver identidade visual, consistência de UI, atualização de tema, revisão de componentes, ajustes de manifest/service worker/ícones PWA, ou padronização de texto de interface em páginas web do GRIS.
---

# Guia de Marca GRIS (Portal + PWA)

## Quando usar
Use esta skill quando a solicitação envolver um ou mais pontos:
- padronização visual de páginas web do GRIS;
- aplicação de tokens de cor, tipografia e espaçamento;
- revisão/criação de componentes de interface;
- ajustes de identidade visual em mobile/desktop;
- atualização de branding no PWA (manifest, tema, ícones, instalação);
- revisão de textos de interface (microcopy) em PT-BR.

## Entregáveis esperados
- Implementação visual aderente aos tokens e componentes canônicos.
- Ajustes de Portal/PWA consistentes com branding vigente.
- Microcopy em PT-BR clara, objetiva e consistente.
- Checklist final cobrindo acessibilidade, responsividade e consistência de marca.

## Fontes canônicas do projeto
Antes de propor qualquer alteração visual, consultar nesta ordem:
1. `gris/public/css/design-system.css`
2. `gris/public/css/components.css`
3. `gris/public/components/`
4. `gris/templates/base.html`
5. `gris/public/manifest.json`

Esses arquivos são a base para evitar drift de marca.

## Fluxo recomendado
1. Identificar a superfície (Portal, PWA ou ambas).
2. Mapear quais tokens/componentes existentes resolvem o pedido.
3. Aplicar padrão canônico antes de criar variações novas.
4. Validar responsividade (desktop + mobile) e acessibilidade mínima.
5. Revisar microcopy PT-BR com tom de voz da marca.
6. Executar checklist final de branding.

## Guias detalhados (ler conforme necessidade)
- Tokens e sistema visual: `references/tokens.md`
- Componentes e estados: `references/components.md`
- Portal + PWA: `references/portal-pwa.md`
- Tom de voz e microcopy PT-BR: `references/voice-ptbr.md`
- Acessibilidade e qualidade visual: `references/accessibility.md`
- Checklist operacional: `assets/checklists.md`
- Catálogo de microcopy: `assets/microcopy-examples.json`

## Regras mandatórias desta skill
- Cor primária oficial: `#0d4d91`.
- Priorizar `var(--token)` em vez de hardcode de cor/spacing.
- Evitar CSS inline quando existir componente/arquivo dedicado.
- Manter consistência entre Portal e PWA (tema/ícones/metadados).
- Toda mudança visual deve preservar legibilidade e foco acessível.

## Anti-padrões
- Introduzir nova cor sem mapear token no design system.
- Duplicar componente existente em `gris/public/components`.
- Ajustar apenas desktop ou apenas mobile em fluxos principais.
- Alterar PWA (manifest/meta) sem checar alinhamento com a marca.
- Escrever microcopy ambígua, agressiva ou inconsistente com PT-BR.

## Checklist final
- [ ] Tokens e componentes canônicos foram priorizados.
- [ ] Ajustes cobrem desktop e mobile com consistência de marca.
- [ ] Portal e PWA permanecem alinhados (manifest, tema, ícones).
- [ ] Microcopy está em PT-BR claro e com terminologia consistente.
- [ ] Requisitos mínimos de acessibilidade visual foram revisados.
