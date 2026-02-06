---
name: frappe-client-scripting
description: Writing Client-side JavaScript for Frappe Desk, Form events, and dialogs.
---

# Frappe Client-Side Scripting

Use this skill when editing `.js` files associated with DocTypes or Desk pages.

## 1. Form Script Pattern

Always wrap code in `frappe.ui.form.on`.

```javascript
frappe.ui.form.on("DocType Name", {
    // Triggered on load
    refresh: function (frm) {
        if (!frm.doc.__islocal) {
            frm.add_custom_button('Button Name', () => {
                // Action
            });
        }
    },
    
    // Triggered when 'field_name' triggers change
    field_name: function (frm) {
        if (frm.doc.field_name) {
            // Logic
        }
    }
});
```

## 2. Child Table Events

```javascript
frappe.ui.form.on("Child DocType Name", {
    // Triggered when a row is added or field in row changes
    child_table_field_name: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        // Logic using 'row'
    }
});
```

## 3. Async Calls (RPC)

Use `frappe.call` to reach whitelisted Python methods.

```javascript
frappe.call({
    method: "app.module.doctype.name.api_method",
    args: {
        arg1: "value"
    },
    freeze: true, // Blocks UI
    freeze_message: "Processing...",
    callback: function (r) {
        if (r.message) {
            frappe.msgprint(r.message);
            // If data changed serverside, refresh
            frm.reload_doc();
        }
    }
});
```

## 4. Form State & Troubleshooting

If the UI does not reflect values set via JS or Server calls:

```javascript
// Reload entire doc from server
frm.reload_doc(); 

// Refresh specific field UI
frm.refresh_field("field_name");
```

## 5. Validation

**Note:** Client-side validation is for UX only. Always replicate validation in Python.

```javascript
if (!frm.doc.required_field) {
    frappe.throw(__("Field is required"));
}
```
