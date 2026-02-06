---
name: frappe-web-portal
description: Developing public-facing web pages, www directories, context management, and frontend components in Frappe.
---

# Frappe Web Portal Development

Use this skill for files in `www/` or `templates/`.

## 1. Structure

*   **Template**: `page_name.html` (Jinja2 + HTML)
*   **Context**: `page_name.py` (Must implement `get_context`)
*   **Static**: `page_name.js` and `page_name.css` (Automatically injected if in same folder)

## 2. Context Logic (`.py`)

```python
import frappe

def get_context(context):
    context.title = "My Page Title"
    context.data = frappe.get_list("My DocType", filters={"published": 1})
    
    # Access Control OBRIGATÓRIO
    from gris.api import portal_access
    if not portal_access.user_has_access(frappe.request.path):
        frappe.local.flags.redirect_location = "/login"
        raise frappe.Redirect
    
    return context
```

## 3. Frontend Logic (`.js`)

*   Use Vanilla JS for simple interactivity.
*   Avoid React/Vue unless building a standalone SPA inside a page.
*   Use standard Frappe/Design System CSS classes.

### Debounce Example (Search)
```javascript
let timeout = null;
document.getElementById('search').addEventListener('input', function(e) {
    clearTimeout(timeout);
    timeout = setTimeout(() => {
        fetchResults(e.target.value);
    }, 500);
});
```

## 4. Components Reuse

Before creating new components, check:
1.  **Base Components**: `/workspace/frappe-bench/apps/gris/gris/public/components`
2.  **Design System**: `/workspace/frappe-bench/apps/gris/gris/public/css/design-system.css`
