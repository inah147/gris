---
name: gris-brand-guide
description: Define e aplica o guia de marca do GRIS para Portal Web e PWA com o design system Basecoat, cobrindo tokens visuais, tema shadcn, macros Jinja, ícones Lucide locais, responsividade, acessibilidade e microcopy PT-BR. Use sempre que o pedido envolver identidade visual, consistência de UI, atualização de tema, revisão de componentes, ajustes de manifest/service worker/ícones PWA, ou padronização de texto de interface em páginas web do GRIS.
---

# Guia de Marca GRIS (Portal + PWA)

## Quando usar
Use esta skill quando a solicitação envolver um ou mais pontos:
- padronização visual de páginas web do GRIS com Basecoat;
- aplicação de tokens de cor, tipografia e espaçamento;
- revisão/criação de componentes de interface do Portal;
- ajustes de identidade visual em mobile/desktop;
- atualização de branding no PWA (manifest, tema, ícones, instalação);
- revisão de textos de interface (microcopy) em PT-BR.

## Entregáveis esperados
- Implementação visual aderente ao Basecoat, tema e componentes canônicos.
- Ajustes de Portal/PWA consistentes com branding vigente.
- Microcopy em PT-BR clara, objetiva e consistente.
- Checklist final cobrindo acessibilidade, responsividade e consistência de marca.

## Fontes canônicas do projeto
Antes de propor qualquer alteração visual, consultar nesta ordem:
1. `gris/public/design_system/README.md`
2. `gris/public/design_system/components/README.md`
3. `gris/public/design_system/docs/components-catalog.md`
4. `gris/public/design_system/css/basecoat.css`
5. `gris/public/design_system/css/theme-shadcn.css`
6. `gris/public/design_system/css/lucide.css`
7. `gris/templates/base.html`
8. `gris/templates/web_sidebar_base.html`
9. `gris/public/manifest.json`

Esses arquivos são a base para evitar drift de marca. `gris/public/css/design-system.css`, `gris/public/css/components.css` e `gris/public/components/` são legado/compatibilidade e não devem guiar novas interfaces quando houver equivalente em Basecoat.

## Fluxo recomendado
1. Identificar a superfície (Portal, PWA ou ambas).
2. Mapear quais tokens/macros Basecoat resolvem o pedido.
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
- O tema Basecoat em `theme-shadcn.css` é a fonte de verdade para cor, tipografia, radius, dark mode e tokens semânticos.
- Priorizar tokens como `--background`, `--foreground`, `--card`, `--primary`, `--muted`, `--border`, `--ring`, `--radius` em vez de hardcode de cor/spacing.
- Usar macros Jinja de `public/design_system/components/generated/` e `public/design_system/components/composed/` antes de criar componente local.
- Inputs de seleção em páginas de Portal devem usar a macro `select` do design system; `<select>` nativo do HTML é anti-padrão de marca porque não segue o tema shadcn nem o padrão visual dos demais componentes.
- Isolar Portal e Desk: Basecoat e `/assets/gris/design_system/*` pertencem às páginas web do Portal, não aos formulários/listas Desk.
- Evitar CSS inline quando existir componente/arquivo dedicado.
- Manter consistência entre Portal e PWA (tema/ícones/metadados).
- Toda mudança visual deve preservar legibilidade e foco acessível.

## Anti-padrões
- Introduzir nova cor sem mapear token no tema Basecoat.
- Duplicar componente existente nas macros Basecoat.
- Usar `<select>` nativo em vez da macro `select` do design system em páginas de Portal.
- Usar `components.css`/`public/components` como base de nova interface quando houver equivalente no design system Basecoat.
- Aplicar Basecoat em Desk ou misturar componentes de Portal com componentes nativos do Frappe.
- Ajustar apenas desktop ou apenas mobile em fluxos principais.
- Alterar PWA (manifest/meta) sem checar alinhamento com a marca.
- Escrever microcopy ambígua, agressiva ou inconsistente com PT-BR.

## Checklist final
- [ ] Tokens, tema e componentes Basecoat foram priorizados.
- [ ] Portal e Desk permanecem isolados quando houver conflito de componentes.
- [ ] Ajustes cobrem desktop e mobile com consistência de marca.
- [ ] Portal e PWA permanecem alinhados (manifest, tema, ícones).
- [ ] Microcopy está em PT-BR claro e com terminologia consistente.
- [ ] Requisitos mínimos de acessibilidade visual foram revisados.
