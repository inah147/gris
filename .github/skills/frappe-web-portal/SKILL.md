---
name: frappe-web-portal
description: Desenvolve e mantém páginas web de Portal no Frappe com `www/`, contexto server-side, assets co-localizados e design system Basecoat. Use quando houver criação/manutenção de rotas de portal, templates Jinja, macros Basecoat/Lucide, scripts, estilos e validação de permissões.
---

# Desenvolvimento Web Portal

## Quando usar
Use esta skill para:
- criar/manter rotas em `gris/www/`;
- implementar `get_context` server-side para páginas web;
- organizar JS/CSS por página com co-location;
- aplicar o design system Basecoat em páginas e componentes do Portal;
- aplicar regras de acesso (público x autenticado) com segurança por padrão.

## Entregáveis esperados
- Rota em `www/` com separação de responsabilidades por arquivo.
- Contexto server-side com validação de acesso quando aplicável.
- Frontend co-localizado com tratamento de estado assíncrono e componentes Basecoat quando houver UI.
- Checklist final cobrindo segurança, isolamento Portal/Desk, reuso, responsividade e consistência visual.

## Princípios mandatórios desta skill
- Permissões devem ser validadas no backend.
- Estrutura por rota deve respeitar co-location por basename.
- Evitar acoplamento global de CSS/JS quando o escopo é local.
- Reutilizar macros Basecoat e componentes do design system antes de criar markup local.
- Isolar componentes do Portal: não usar Basecoat em telas Desk nem alterar componentes nativos do Frappe para resolver demanda de `www`.
- Garantir funcionalidade e legibilidade em desktop e mobile.

## Estrutura obrigatória por tipo de arquivo (`www`)
Cada arquivo deve conter apenas o tipo de código correspondente:

- `*.html` / `*.md` → markup/template da página (Jinja/HTML/Markdown).
- `*.py` → lógica server-side (ex.: `get_context`, checagem de acesso, montagem de contexto).
- `*.js` → comportamento frontend da rota.
- `*.css` → estilo específico da rota.

Não misturar lógica Python em HTML, nem CSS/JS inline quando houver arquivo dedicado.

## Basecoat no Portal
O design system canônico do Portal fica em `gris/public/design_system/`.

Fontes de verdade:
- `gris/public/design_system/README.md`
- `gris/public/design_system/components/README.md`
- `gris/public/design_system/docs/components-catalog.md`
- `gris/public/design_system/css/basecoat.css`
- `gris/public/design_system/css/theme-shadcn.css`
- `gris/public/design_system/css/lucide.css`

Assets globais do Portal são carregados em `gris/templates/base.html`. Para páginas autenticadas com navegação lateral/topbar, prefira estender `templates/web_sidebar_base.html`, que já usa sidebar, dropdown e ícones do design system.

### Imports Jinja recomendados
Use macros geradas para componentes interativos e macros compostas para elementos CSS-only:

```jinja
{% from "public/design_system/components/generated/select.html.jinja" import select %}
{% from "public/design_system/components/generated/tabs.html.jinja" import tabs %}
{% from "public/design_system/components/generated/toast.html.jinja" import toaster %}
{% from "public/design_system/components/composed/basecoat-composed.html.jinja" import card, button, field, empty %}
{% from "public/design_system/components/composed/lucide.html.jinja" import lucide_icon %}
```

Componentes disponíveis incluem `command`, `dialog`, `dropdown-menu`, `popover`, `select`, `sidebar`, `tabs`, `toast`, além de macros compostas como `alert`, `avatar`, `badge`, `button`, `card`, `field`, `form`, `input`, `table`, `skeleton`, `spinner`, `switch` e `tooltip`.

### Selects
Em páginas de Portal, usar **sempre** a macro `select` de `public/design_system/components/generated/select.html.jinja`. Nunca usar `<select>` nativo do HTML (mesmo com `class="select"`) — o macro é a forma oficial: UI consistente com o tema shadcn, acessibilidade, suporte a `combobox`/`multiple` e integração com o observer do Basecoat.

Em formulários que usam `FormData` / submit nativo, passar `name="..."` para o macro. O macro renderiza um `<input type="hidden" name="...">` interno, atualizado pelo `select.js` a cada seleção, então `new FormData(form)` devolve o valor corrente.

Para redefinir o componente visualmente após `form.reset()`, iterar sobre `form.querySelectorAll('.select')` e setar `el.value = ''` (a propriedade é exposta pelo componente). O reset nativo do `<form>` limpa apenas o hidden input, mas não o label do trigger.

### JS e atualização dinâmica
- Componentes Basecoat são inicializados por `basecoat.min.js`, scripts em `design_system/js/components/` e `design-system-init.js`.
- Para HTML inserido dinamicamente, o observer do Basecoat cobre novos nós; se necessário, dispare `document.dispatchEvent(new CustomEvent("gris:design-system:init"))`.
- Para toasts, renderize o `toaster()` na página quando houver feedback dinâmico e dispare `basecoat:toast` no client.

### CSS local da rota
- Use CSS co-localizado (`www/rota.css`) apenas para layout específico da página.
- Prefira classes e tokens Basecoat (`--background`, `--foreground`, `--card`, `--primary`, `--muted`, `--border`, `--ring`, `--radius`) em vez de criar uma camada paralela.
- `gris/public/css/design-system.css`, `gris/public/css/components.css` e `gris/public/components/` são legado/compatibilidade; não usar como primeira opção em nova interface.

## Convenção de nome e auto-carregamento
Para rotas em `www`, use o **mesmo nome base** para arquivos relacionados:

- `minha_pagina.html`
- `minha_pagina.py`
- `minha_pagina.js`
- `minha_pagina.css`

Quando os arquivos coexistem com o mesmo basename:
- o controller Python co-localizado é resolvido automaticamente;
- JS e CSS co-localizados são incluídos automaticamente no render.

### Regras importantes
1. Se o arquivo da rota for `minha-pagina.html`, o módulo Python esperado é `minha_pagina.py` (hífen vira underscore no módulo).
2. O auto-carregamento de `*.js`/`*.css` co-localizado pode ser sobrescrito pelo próprio template ao definir blocos Jinja de script/style.
3. Arquivos Python em `www` não são páginas renderizáveis por si só; são controladores da rota/template correspondente.

## Padrão de separação por rota
Para cada rota web, prefira a organização:

- `www/rota.html` → estrutura visual
- `www/rota.py` → contexto + segurança
- `www/rota.js` → interações do cliente
- `www/rota.css` → estilo local

Para casos não-HTML também suportados em `www`, manter o mesmo padrão de pareamento:
- `robots.txt` + `robots.py`
- `sitemap.xml` + `sitemap.py`
- `website_script.js` + `website_script.py`

## Permissões (regra obrigatória desta skill)
**Sempre validar permissões no backend** (`*.py`), exceto quando o requisito pedir explicitamente que a página seja pública.

Diretriz padrão:
- página privada/autenticada: validar usuário/permissão no `get_context` e redirecionar/bloquear quando necessário;
- página pública: permitir guest somente quando isso estiver explícito no requisito.

Referências de padrão em `www`:
- fluxo protegido: `frappe/www/me.py`, `frappe/www/app.py`;
- fluxo público: `frappe/www/login.py`.

## Contexto server-side (exemplo)
```python
import frappe

def get_context(context):
    context.title = "Minha Página"
    context.data = frappe.get_list("My DocType", filters={"published": 1})

    from gris.api import portal_access
    if not portal_access.user_has_access(frappe.request.path):
        frappe.local.flags.redirect_location = "/login"
        raise frappe.Redirect

    return context
```

## Boas práticas frontend
- Preferir JS vanilla para interações simples.
- Não introduzir framework pesado sem necessidade clara.
- Tratar loading/erro em chamadas assíncronas.
- Manter escopo por rota: evitar CSS/JS global quando o uso for local.
- Usar componentes Basecoat para controles comuns antes de criar markup local.
- Não importar `/assets/gris/design_system/*` nem macros de portal em scripts ou telas Desk.

## Responsividade e identidade visual por dispositivo
- Toda implementação de portal deve funcionar corretamente em **desktop e mobile**.
- A interface deve ser responsiva por padrão (layout fluido, breakpoints e componentes adaptáveis).
- Considerar que a identidade visual é **ligeiramente diferente** entre desktop e mobile (hierarquia, espaçamento, densidade e tamanho de elementos), mantendo coerência da marca.
- As diferenças entre desktop e mobile devem ser intencionais e definidas no CSS da rota/componente, sem quebrar consistência funcional.

## Reuso de componentes
Antes de criar componente novo, revisar:
1. `gris/public/design_system/docs/components-catalog.md`
2. `gris/public/design_system/components/generated/`
3. `gris/public/design_system/components/composed/basecoat-composed.html.jinja`
4. `gris/public/design_system/components/composed/lucide.html.jinja`
5. Legado apenas quando necessário: `gris/public/css/components.css`, `gris/public/css/design-system.css`, `gris/public/components/`

## Checklist obrigatório antes de concluir uma rota
- [ ] Arquivos separados por responsabilidade (`.html/.py/.js/.css`).
- [ ] Nomes alinhados por basename para auto-resolução.
- [ ] Permissão validada no backend (exceto quando explicitamente pública).
- [ ] JS/CSS no escopo da rota, sem acoplamento global desnecessário.
- [ ] Componentes Basecoat/macros Jinja reaproveitados quando possível.
- [ ] Nenhum componente/asset do Portal foi introduzido no Desk.
- [ ] Fluxo validado em desktop e mobile.
- [ ] Ajustes de identidade visual por dispositivo aplicados com consistência.

## Anti-padrões (evitar)
- Criar rota em `www` sem arquivo `*.py` de contexto quando houver qualquer regra de negócio ou acesso.
- Assumir página pública por padrão sem requisito explícito.
- Fazer checagem de permissão apenas no frontend (JS): validação de acesso é backend.
- Misturar CSS/JS inline no HTML quando houver arquivo co-localizado dedicado.
- Usar nomes diferentes entre arquivos da mesma rota (quebra co-location e auto-resolução).
- Duplicar componente já existente em vez de reutilizar macros Basecoat.
- Usar `gris/public/components` ou `components.css` como padrão de nova UI quando existir equivalente em Basecoat.
- Usar `<select>` nativo em página de Portal quando existe a macro `select` do design system.
- Carregar Basecoat ou macros de Portal no Desk para corrigir formulário, list view ou dashboard interno do Frappe.
- Colocar lógica de API pesada diretamente no template em vez de centralizar em Python.
- Entregar página apenas para desktop ou apenas para mobile.
- Forçar identidade visual idêntica entre desktop/mobile quando o canal exige ajustes leves de UI.
