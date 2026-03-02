# Tokens de Marca do GRIS

## Fonte da verdade
- `gris/public/css/design-system.css`

## Cores
### Primária (oficial)
- `--color-primary: #0d4d91`
- `--color-primary-hover: #0b3d73`
- `--color-primary-active: #093159`
- `--color-primary-light: #e8f1f9`

### Semânticas
- Sucesso: `--color-success*`
- Erro: `--color-danger*`
- Aviso: `--color-warning*`
- Informação: `--color-info*`

### Neutras e texto
- Fundo página/card: `--bg-page`, `--bg-card`
- Texto: `--text-primary`, `--text-secondary`, `--text-muted`
- Borda: `--border-color*`

## Tipografia
### Famílias
- Principal: `--font-sans`
- Monoespaçada: `--font-mono`

### Escala
- `--text-xs` até `--text-4xl`

### Peso e ritmo
- Pesos: `--font-normal`, `--font-medium`, `--font-semibold`, `--font-bold`
- Entrelinha: `--leading-tight` até `--leading-loose`

## Espaçamento e layout
- Escala principal: `--space-xs` até `--space-4xl`
- Layout base: `--container-max-width`, `--sidebar-width`, `--topbar-height`

## Radius, sombras e motion
- Radius: `--radius-xs` até `--radius-full`
- Sombras: `--shadow-xs` até `--shadow-2xl` + variantes (`--shadow-card`, `--shadow-modal`)
- Transições: `--transition-fast`, `--transition-base`, `--transition-slow`

## Regras de uso
1. Nunca usar valor hardcoded se já existir token equivalente.
2. Ao criar novo token, manter padrão de nomenclatura `--categoria-variacao`.
3. Evitar “quase igual”: reutilizar token existente para preservar consistência.
4. Em estado de foco/hover/active, usar variações já definidas em vez de inventar novas.

## Anti-padrões
- Definir `color: #...` direto em componente compartilhado sem necessidade.
- Misturar escalas de spacing fora do sistema de tokens.
- Aplicar sombras densas em telas mobile sem justificativa.
