# Web Development Standards

Padrões para desenvolvimento web em `www/` e `public/`.

## Estrutura de Pasta Padrão

```
www/
├── admin/
│   ├── dashboard/
│   │   ├── dashboard.py
│   │   ├── dashboard.html
│   │   ├── dashboard.js
│   │   ├── styles/
│   │   │   └── dashboard.css
│   │   └── components/
│   │       ├── charts.js
│   │       └── stats.js
│   └── settings/
│       └── ...
└── portal/
    └── ...

public/
├── components/
│   ├── data-table/
│   ├── modal/
│   ├── form-builder/
│   └── filter-panel/
├── utils/
│   ├── api-client.js
│   ├── form-helpers.js
│   └── validators.js
├── lib/
│   ├── frappe-bridge.js
│   └── event-emitter.js
└── styles/
    ├── theme.css
    ├── variables.css
    └── responsive.css
```

## File Naming Conventions

- **Files**: `kebab-case` (data-table.js, user-profile.html)
- **Components**: `PascalCase` (DataTable, UserProfile)
- **Classes**: `PascalCase` (class DataTable {})
- **Methods**: `camelCase` (getData(), renderTable())
- **Constants**: `UPPER_SNAKE_CASE` (MAX_ITEMS, DEFAULT_LIMIT)

## HTML/Template Standards

```html
<!-- Use semantic HTML -->
<header class="page-header">
    <h1>Página Title</h1>
</header>

<main class="page-content">
    <section id="data-section">
        <!-- Content -->
    </section>
</main>

<!-- Always include meta tags -->
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="Descrição da página">
<meta name="charset" content="UTF-8">
```

## JavaScript Standards

```javascript
// 1. Use const/let, não var
const dataTable = new DataTable();
let currentPage = 1;

// 2. Use arrow functions
const getData = () => {
    // ...
};

// 3. Use template literals
const html = `<div>${variable}</div>`;

// 4. Error handling obrigatório
try {
    const data = await fetchData();
} catch (error) {
    console.error('Error:', error);
}

// 5. Comentários explicando WHY, não WHAT
// Usar cache para reduzir queries ao servidor
const cachedData = localStorage.getItem('key');
```

## CSS Standards

```css
/* 1. Use CSS variables */
:root {
    --primary-color: #3498db;
    --spacing: 1rem;
}

/* 2. BEM Naming */
.component__element--modifier

/* 3. Organize por categoria */
/* Positioning */
/* Display & Box Model */
/* Color */
/* Text */
/* Other */

/* 4. Mobile-first responsive */
.element { }
@media (min-width: 768px) { }
```

## Performance Guidelines

- Images < 100KB (lazy load > 50KB)
- CSS/JS minified in production
- No render-blocking resources
- Gzip compression enabled
- Browser caching enabled
- CDN para static assets

## Performance Metrics

- **First Contentful Paint (FCP)**: < 1.8s
- **Largest Contentful Paint (LCP)**: < 2.5s
- **First Input Delay (FID)**: < 100ms
- **Cumulative Layout Shift (CLS)**: < 0.1
- **Time to Interactive (TTI)**: < 3.8s

## Accessibility Standards

```html
<!-- Semantic HTML -->
<button>Click me</button>
<nav aria-label="Main navigation">...</nav>
<section aria-labelledby="section-title">...</section>

<!-- Form accessibility -->
<label for="email">Email Address</label>
<input id="email" type="email" aria-describedby="email-hint">
<small id="email-hint">We'll never share your email</small>

<!-- Images -->
<img src="photo.jpg" alt="Descrição clara e concisa">

<!-- Skip links -->
<a href="#main-content" class="skip-link">Skip to main content</a>
```

## Testing Checklist

- [ ] Desktop (Chrome, Firefox, Safari, Edge)
- [ ] Mobile (iOS, Android)
- [ ] Tablet
- [ ] Accessible (keyboard navigation, screen reader)
- [ ] Network throttling (slow 3G)
- [ ] Lighthouse score > 80

## Security

- Validate all inputs server-side
- Sanitize HTML output
- Use CSRF tokens
- No credentials in frontend code
- HTTPS only in production
- Content Security Policy headers

## Git Workflow

```bash
# Feature branch
git checkout -b feat/component-name

# Commit structure
git commit -m "feat: description"
git commit -m "fix: description"
git commit -m "refactor: description"

# Pull request antes de merge
```

## Code Review Checklist

- [ ] Código funciona sem errors
- [ ] Performance considerada
- [ ] Accessibility implementada
- [ ] Responsivo em todos devices
- [ ] Não há código duplicado
- [ ] Documentação atualizada
- [ ] Commits bem estruturados

## Component Documentation Template

```markdown
# ComponentName

Brief description of what the component does.

## Features
- Feature 1
- Feature 2
- Feature 3

## Installation
\`\`\`javascript
<link rel="stylesheet" href="/public/components/component-name/component-name.css">
<script src="/public/components/component-name/component-name.js"></script>
\`\`\`

## Basic Usage
\`\`\`javascript
const component = new ComponentName({
    container: '#app',
    data: [...]
});
component.render();
\`\`\`

## API Reference

### Methods
- \`render()\` - Renderiza o componente
- \`update(data)\` - Atualiza dados
- \`destroy()\` - Destroy do componente

### Events
- \`update\` - Disparado quando dados são atualizados
- \`error\` - Disparado quando há erro

## Browser Support
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+
```

## Color Standards

Use CSS variables para cores:
```css
:root {
    --color-primary: #3498db;
    --color-success: #27ae60;
    --color-danger: #e74c3c;
    --color-warning: #f39c12;
    --color-info: #2980b9;
    --color-text: #2c3e50;
    --color-border: #ecf0f1;
    --color-bg: #ffffff;
}
```

## Spacing Standards

Use valores consistentes:
```css
--space-xs: 0.25rem;    /* 4px */
--space-sm: 0.5rem;     /* 8px */
--space-md: 1rem;       /* 16px */
--space-lg: 1.5rem;     /* 24px */
--space-xl: 2rem;       /* 32px */
--space-2xl: 3rem;      /* 48px */
```

## Typography Standards

```css
/* Font sizes */
--font-xs: 0.75rem;     /* 12px */
--font-sm: 0.875rem;    /* 14px */
--font-base: 1rem;      /* 16px */
--font-lg: 1.125rem;    /* 18px */
--font-xl: 1.25rem;     /* 20px */
--font-2xl: 1.5rem;     /* 24px */
--font-3xl: 1.875rem;   /* 30px */
```

## Component Maturity Levels

### Level 1: Experimental
- Pode mudar significativamente
- Não recomendado para produção
- Tag: `experimental`

### Level 2: Stable
- API estável
- Testado em navegadores múltiplos
- Pronto para produção
- Tag: `stable`

### Level 3: Mature
- Usado em múltiplos projetos
- Performance otimizada
- Documentação completa
- Tag: `mature`

Use tags em `package.json`:
```json
{
    "name": "component-name",
    "maturity": "stable",
    "version": "1.0.0"
}
```
