---
name: frappe-api-design
description: Designing and implementing REST APIs, RPC Whitelisted functions, and standardized responses in Frappe.
---

# Frappe API Design

Use this skill when creating API endpoints or exposing methods to the client.

## 1. Whitelisted Functions (RPC)

For direct Client-to-Server calls via `frappe.call`.

```python
@frappe.whitelist()
def update_status(name, status):
    # 1. Security Check (Explicit)
    if not frappe.db.has_permission("My DocType", "write", name):
        frappe.throw("Permission Denied", frappe.PermissionError)

    # 2. Logic
    doc = frappe.get_doc("My DocType", name)
    doc.status = status
    doc.save()
    
    return doc.status
```

*   **@frappe.whitelist(allow_guest=True)**: Use carefully for public endpoints.

## 2. REST API Standards

When designing APIs for external consumers:

*   **Stateless**: Do not rely on session cookies if possible.
*   **Filters**: Accept JSON strings for complex filtering: `filters=[["field","=","value"]]`.
*   **Pagination**: Respect `limit_start` and `limit_page_length`.

## 3. Response Structure

Frappe automatically wraps return values in `{"message": ...}` for RPC calls.
For pure REST, you can use `frappe.response` customization or return dicts.
