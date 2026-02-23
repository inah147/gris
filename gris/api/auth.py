from urllib.parse import urlparse

import frappe
from werkzeug.exceptions import HTTPException


class TemporaryRedirect(HTTPException):
	code = 302
	description = "Temporary Redirect"

	def __init__(self, location: str):
		super().__init__()
		self.location = location

	def get_headers(self, environ=None, scope=None):
		return [("Location", self.location)]


def _has_desk_access(user: str) -> bool:
	if not user or user == "Guest":
		return False

	return "Acesso ao Desk" in frappe.get_roles(user)


def _is_desk_redirect(redirect_to: str | None) -> bool:
	if not redirect_to or not isinstance(redirect_to, str):
		return False

	path = urlparse(redirect_to).path or redirect_to
	normalized_path = path.strip().lower()

	return (
		normalized_path == "/app"
		or normalized_path.startswith("/app/")
		or normalized_path == "/desk"
		or normalized_path.startswith("/desk/")
	)


def enforce_no_desk_redirect():
	user = frappe.session.user if getattr(frappe.local, "session", None) else "Guest"
	if not user or user == "Guest":
		return

	if _has_desk_access(user):
		return

	request = getattr(frappe.local, "request", None)
	request_path = (getattr(request, "path", "") or "").strip().lower()

	if request_path in {"/app", "/desk"} or request_path.startswith("/app/") or request_path.startswith("/desk/"):
		raise TemporaryRedirect(location="/inicio")


@frappe.whitelist(allow_guest=True, methods=["POST"])
def update_password(
	new_password: str, logout_all_sessions: int = 0, key: str | None = None, old_password: str | None = None
):
	from frappe.core.doctype.user.user import update_password as core_update_password

	redirect_to = core_update_password(
		new_password=new_password,
		logout_all_sessions=logout_all_sessions,
		key=key,
		old_password=old_password,
	)

	if _has_desk_access(frappe.session.user):
		return redirect_to

	if _is_desk_redirect(redirect_to):
		return "/inicio"

	return redirect_to
