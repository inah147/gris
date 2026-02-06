---
name: frappe-doctype-schema
description: Creating and modifying Frappe DocTypes, JSON schemas, and enforcing naming conventions.
---

# Frappe DocType Standards

Use this skill when defining new DocTypes or modifying `schema.json` files.

## Naming Conventions (Namespaces)

*   **DocType Name**: `PascalCase` (e.g., `Customer`, `Sales Order`).
*   **Prefix**: Always use the app name prefix to avoid conflicts if not in the core `frappe` / `erpnext` app.
*   **Fields**: `snake_case` (e.g., `customer_name`, `is_active`).
*   **Foreign Keys**: `{doctype_name}_id` or simply `name` if referring to the ID column.

## JSON Structure

Follow this standard structure for `*.json` definitions:

```json
{
  "doctype": "CamelCase",
  "module": "snake_case_app",
  "fields": [
    {
      "fieldname": "title",
      "fieldtype": "Data",
      "label": "Title",
      "reqd": 1,
      "in_list_view": 1
    },
    {
      "fieldname": "status",
      "fieldtype": "Select",
      "label": "Status",
      "options": "Open\nClosed",
      "default": "Open"
    }
  ],
  "permissions": [
    {
      "role": "System Manager",
      "read": 1,
      "write": 1,
      "create": 1,
      "delete": 1
    }
  ]
}
```

## Checklist
- [ ] Is the module correct (snake_case)?
- [ ] Are fieldnames snake_case?
- [ ] Are permissions explicitly defined?
