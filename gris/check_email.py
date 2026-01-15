import json

import frappe


def check_email_queue():
	output = []
	emails = frappe.get_all(
		"Email Queue",
		fields=["name", "sender", "recipient", "subject", "status", "message", "creation"],
		order_by="creation desc",
		limit=5,
	)

	output.append(f"Found {len(emails)} emails in queue.")
	for email in emails:
		output.append(
			f"[{email.creation}] To: {email.recipient} | Subject: {email.subject} | Status: {email.status}"
		)

	# Check Error Logs again just in case
	output.append("\nLast Errors:")
	errors = frappe.get_all(
		"Error Log", fields=["method", "error", "creation"], order_by="creation desc", limit=2
	)
	if errors:
		for e in errors:
			output.append(f"[{e.creation}] {e.method}: {e.error[:200]}...")

	return "\n".join(output)
