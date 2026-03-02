---
name: frappe-web-portal
description: Desenvolve e mantém páginas web no Frappe com `www/`, separação por tipo de arquivo, contexto server-side e assets co-localizados. Use quando houver criação/manutenção de rotas de portal, templates Jinja, scripts e validação de permissões.
---

# Desenvolvimento Web Portal

## Quando usar
Use esta skill para:
- criar/manter rotas em `gris/www/`;
- implementar `get_context` server-side para páginas web;
- organizar JS/CSS por página com co-location;
- aplicar regras de acesso (público x autenticado) com segurança por padrão.

## Estrutura obrigatória por tipo de arquivo (`www`)
Cada arquivo deve conter apenas o tipo de código correspondente:

- `*.html` / `*.md` → markup/template da página (Jinja/HTML/Markdown).
- `*.py` → lógica server-side (ex.: `get_context`, checagem de acesso, montagem de contexto).
- `*.js` → comportamento frontend da rota.
- `*.css` → estilo específico da rota.

Não misturar lógica Python em HTML, nem CSS/JS inline quando houver arquivo dedicado.

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

## Responsividade e identidade visual por dispositivo
- Toda implementação de portal deve funcionar corretamente em **desktop e mobile**.
- A interface deve ser responsiva por padrão (layout fluido, breakpoints e componentes adaptáveis).
- Considerar que a identidade visual é **ligeiramente diferente** entre desktop e mobile (hierarquia, espaçamento, densidade e tamanho de elementos), mantendo coerência da marca.
- As diferenças entre desktop e mobile devem ser intencionais e definidas no CSS da rota/componente, sem quebrar consistência funcional.

## Reuso de componentes
Antes de criar componente novo, revisar:
1. `gris/public/components`
2. `gris/public/css/design-system.css`

## Checklist obrigatório antes de concluir uma rota
- [ ] Arquivos separados por responsabilidade (`.html/.py/.js/.css`).
- [ ] Nomes alinhados por basename para auto-resolução.
- [ ] Permissão validada no backend (exceto quando explicitamente pública).
- [ ] JS/CSS no escopo da rota, sem acoplamento global desnecessário.
- [ ] Componentes reaproveitados quando possível.
- [ ] Fluxo validado em desktop e mobile.
- [ ] Ajustes de identidade visual por dispositivo aplicados com consistência.

## Anti-padrões (evitar)
- Criar rota em `www` sem arquivo `*.py` de contexto quando houver qualquer regra de negócio ou acesso.
- Assumir página pública por padrão sem requisito explícito.
- Fazer checagem de permissão apenas no frontend (JS): validação de acesso é backend.
- Misturar CSS/JS inline no HTML quando houver arquivo co-localizado dedicado.
- Usar nomes diferentes entre arquivos da mesma rota (quebra co-location e auto-resolução).
- Duplicar componente já existente em vez de reutilizar `gris/public/components`.
- Colocar lógica de API pesada diretamente no template em vez de centralizar em Python.
- Entregar página apenas para desktop ou apenas para mobile.
- Forçar identidade visual idêntica entre desktop/mobile quando o canal exige ajustes leves de UI.
