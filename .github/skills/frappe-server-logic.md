---
name: frappe-server-logic
description: Implementing Python server-side logic, controllers, document validation, and database operations in Frappe.
---

# Frappe Server-Side Logic (Python)

Use this skill when writing controllers (`.py` files matching DocTypes), scripts, or utility functions.

## 1. Document Controller Pattern

Controllers must inherit from `Document` and implement specific hook methods.

```python
import frappe
from frappe.model.document import Document

class MyDocType(Document):
    def validate(self):
        """Runs before save (insert or update). Use for data validation."""
        self.validate_values()
    
    def before_save(self):
        """Runs before database commit."""
        pass

    def on_submit(self):
        """Runs on document submission."""
        pass

    def validate_values(self):
        if self.field_value < 0:
            frappe.throw("Error Message") 
```

## 2. Common Operations

### Fetching Data
```python
# Single Document (ORM)
doc = frappe.get_doc("DocType", "name_id")

# List of Dictionaries (Optimized)
data = frappe.get_list("Sales Order", 
    filters={"status": "Open"}, 
    fields=["name", "customer", "grand_total"]
)

# Raw SQL (Only if ORM is insufficient)
# ALWAYS use parameters to prevent SQL Injection
frappe.db.sql("SELECT name FROM `tabCustomer` WHERE name = %s", (customer_name,))
```

## 3. Data Consistency

Always use `doc.save()` over `frappe.db.set_value` when business logic (hooks) needs to run.

```python
# ✅ Logic runs (validate, on_update)
doc = frappe.get_doc("Order", "123")
doc.total = 100
doc.save()

# ❌ Logic skipped (Direct DB update)
frappe.db.set_value("Order", "123", "total", 100)
```

## 4. Logging
```python
frappe.logger().info(f"Operation completed: {data}")
```
