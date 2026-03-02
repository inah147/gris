# Componentes e padrões de UI

## Fontes canônicas
- `gris/public/css/components.css`
- `gris/public/components/`

## Princípios
1. Reusar antes de criar.
2. Compor com tokens do design system.
3. Garantir estados visuais completos: default, hover, focus, active, disabled.

## Componentes prioritários
- Botões: `public/components/buttons/buttons.css`
- Cards: `public/components/cards/cards.css`
- Layout: `public/components/layout/layout.css`
- Badges: `public/components/badges/badges.css`

## Regras de implementação
- Botões primários devem refletir `--color-primary` e variações de estado.
- Formulários devem manter altura, padding e borda a partir de tokens (`--input-*`).
- Cards e painéis devem usar radius/sombra da escala padrão.
- Evitar criar “variante local” sem necessidade de negócio clara.

## Estados e feedback
- Loading: indicar ação em andamento sem bloquear leitura.
- Erro: usar cor semântica + mensagem clara e orientada à ação.
- Sucesso: curto, objetivo e com próximo passo quando relevante.

## Anti-padrões
- Componente novo sem inventário prévio do diretório `public/components`.
- CSS inline para estado visual recorrente.
- Estado de foco invisível.
