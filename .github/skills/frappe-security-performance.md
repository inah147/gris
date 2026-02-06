---
name: frappe-security-performance
description: Implementation of security best practices (permissions, sanitization) and performance optimizations (caching, query tuning) in Frappe.
---

# Security & Performance

Use this skill to audit code or implement complex logic safely.

## Security Best Practices

### 1. Permissions
Never assume the user has access just because they are logged in.

```python
# Check DocType level permission
if not frappe.db.has_permission("DocType", "read", doc_name):
    frappe.throw("Not Permitted")

# Check explicit User permissions if needed
if doc.owner != frappe.session.user:
    frappe.throw("Not Owner")
```

### 2. SQL Injection Prevention
**NEVER** format strings into SQL queries.

```python
# ❌ Dangerous
frappe.db.sql(f"select name from tabCustomer where name = '{name}'") 

# ✅ Safe
frappe.db.sql("select name from tabCustomer where name = %s", (name,))
```

### 3. XSS Protection
Output user-generated HTML content safely.
```python
frappe.utils.html_escape(user_input)
```

## Performance Optimization

### 1. Avoid N+1 Queries
Do not run queries inside loops.

```python
# ❌ N+1
for order in orders:
    # This queries DB for every iteration
    customer = frappe.get_doc("Customer", order.customer)

# ✅ Optimized
orders = frappe.get_list("Sales Order", fields=["name", "customer_name", "grand_total"])
# OR use SQL JOINs if simple fetching isn't enough
```

### 2. Caching
Store expensive calculations or config data.

```python
value = frappe.cache().get_value("unique_key")
if not value:
    value = expensive_calculation()
    frappe.cache().set_value("unique_key", value, expires_in_sec=300)
return value
```

### 3. Background Jobs
Offload heavy processing (emails, report generation, complex updates).

```python
frappe.enqueue(
    method="app.module.method_name",
    queue="long", 
    timeout=300,
    param1=value
)
```
