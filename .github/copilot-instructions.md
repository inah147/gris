# Frappe Development Copilot Instructions

This repository follows strict development standards for the Frappe Framework.

## 🧠 Agent Skills System

Specific implementation details have been offloaded to **Agent Skills**. 
Refer to them for detailed implementation code:

| Type of Work | Skill to Use |
| :--- | :--- |
| **Python / Backend** | `@frappe-server-logic` (Controllers, Hooks, DB) |
| **JavaScript / Desk** | `@frappe-client-scripting` (Form API, Events) |
| **DocType / Schema** | `@frappe-doctype-schema` (JSON, Naming) |
| **Web Portal / www** | `@frappe-web-portal` (Jinja, Context, Frontend) |
| **API Endpoints** | `@frappe-api-design` (Whitelisting, REST) |
| **Security & Speed** | `@frappe-security-performance` (Permissions, Optimization) |

## 🏗 Project Structure

```
your_app/
├── your_app/                 # App package
│   ├── __init__.py
│   ├── hooks.py              # App Hooks
│   ├── modules.txt           # Declared Modules
│   └── your_module/          # Module Directory
│       ├── doctype/
│       │   └── your_doctype/ # DocType Definition
│       ├── report/
│       ├── page/
│       └── api.py            # API implementations
└── tests/                    # Unit Tests
```

## 📋 Git Workflow & Commits

1.  **Branching**: `git checkout -b feature/name-of-feature`
2.  **Commit Messages**:
    *   `feat: description` (New features)
    *   `fix: description` (Bug fixes)
    *   `docs: description` (Documentation)
3.  **Merge**: Push to origin `feature/branch`.

## 🤝 Agent Communication (Handoffs)

When specific domain knowledge is required, Agents should handoff context:

1.  **Architecture/Schema** → `@frappe-doctype-schema`
2.  **Backend Implementation** → `@frappe-server-logic`
3.  **Frontend Implementation** → `@frappe-client-scripting`
4.  **Review/Audit** → `@frappe-security-performance`

**Example Handoff Flow:**
> "I have planned the Schema (Doctype). Now switching to **frappe-server-logic** to implement the validation hooks."

## ✅ Pre-Commit Checklist

Before generating final code or committing, verify:

- [ ] **Linter**: Code passes standard linters.
- [ ] **Debug**: No `console.log` or `print` statements.
- [ ] **Validation**: Server-side validation defaults are set.
- [ ] **Permissions**: `has_permission` checks are present.
- [ ] **Optimization**: No queries inside loops (N+1).

## 🆘 Troubleshooting & Resources

*   **Documentation**: [docs.frappe.io](https://docs.frappe.io)
*   **Framework Source**: `/frappe` folder in workspace.
*   **Issues**:
    *   If Form state isn't updating → Check `@frappe-client-scripting` (reload_doc).
    *   If Data isn't saving → Check `@frappe-server-logic` (doc.save vs set_value).
