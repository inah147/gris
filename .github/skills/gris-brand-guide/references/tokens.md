# Tokens de Marca do GRIS

## Fonte da verdade
- `gris/public/design_system/css/theme-shadcn.css`
- `gris/public/design_system/css/basecoat.css`
- `gris/public/design_system/css/lucide.css`

`theme-shadcn.css` define a identidade visual do Portal sobre Basecoat. `basecoat.css` fornece classes e tokens compilados. Não impor hex hardcoded na skill: se a marca mudar, atualize o tema canônico.

## Tokens principais
### Superfícies e texto
- `--background`
- `--foreground`
- `--card`
- `--card-foreground`
- `--popover`
- `--popover-foreground`

### Ações e estados
- `--primary`
- `--primary-foreground`
- `--secondary`
- `--secondary-foreground`
- `--destructive`
- `--accent`
- `--accent-foreground`
- `--muted`
- `--muted-foreground`

### Estrutura
- `--border`
- `--input`
- `--ring`
- `--radius`

### Sidebar e gráficos
- `--sidebar*`
- `--chart-1` até `--chart-5`

## Tipografia
- O Portal usa Figtree local via `@font-face` em `theme-shadcn.css`.
- Use `--font-sans` e classes Basecoat para escala, peso e ritmo.
- Evite definir família tipográfica local em página, exceto por necessidade pontual e justificada.

## Radius, foco e motion
- Radius vem de `--radius` e derivados (`--radius-sm`, `--radius-md`, `--radius-lg`, `--radius-xl`).
- Foco deve usar `--ring`/estados Basecoat, nunca ficar invisível.
- Transições devem seguir o padrão Basecoat e não criar animações locais ruidosas.

## Compatibilidade legado
`gris/public/css/design-system.css` ainda pode existir para páginas antigas. Em nova UI, use Basecoat como fonte primária; só mencione tokens legados quando estiver mantendo página que já depende deles.

## Regras de uso
1. Nunca usar valor hardcoded se já existir token equivalente.
2. Ao criar novo token, preferir adicioná-lo ao tema canônico em vez de CSS local disperso.
3. Evitar “quase igual”: reutilizar token existente para preservar consistência.
4. Em estado de foco/hover/active, usar estados e classes Basecoat antes de inventar variações.

## Anti-padrões
- Definir `color: #...` direto em componente compartilhado sem necessidade.
- Misturar tokens legados e Basecoat sem motivo claro.
- Aplicar sombras densas em telas mobile sem justificativa.
