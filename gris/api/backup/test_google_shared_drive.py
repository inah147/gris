# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

import datetime

import frappe
from frappe.tests.utils import FrappeTestCase
from googleapiclient.errors import HttpError

from gris.api.backup import google_shared_drive as backup_module


class _DummyHttpResponse:
	def __init__(self, status_code):
		self.status = status_code
		self.reason = "Test"


class _FakeRequest:
	def __init__(self, executor):
		self._executor = executor

	def execute(self):
		return self._executor()


class _FakeFilesResource:
	def __init__(self, list_pages, delete_behaviors=None):
		self.list_pages = list_pages
		self.delete_behaviors = delete_behaviors or {}
		self.list_calls = []
		self.delete_calls = []
		self._list_index = 0

	def list(self, **kwargs):
		index = self._list_index
		self._list_index += 1
		self.list_calls.append(kwargs)

		return _FakeRequest(
			lambda: (
				self.list_pages[index]
				if index < len(self.list_pages)
				else {"files": [], "nextPageToken": None}
			)
		)

	def delete(self, fileId, supportsAllDrives=True):
		self.delete_calls.append(fileId)
		behavior = self.delete_behaviors.get(fileId, "ok")

		def _execute():
			if isinstance(behavior, Exception):
				raise behavior

			if callable(behavior):
				return behavior()

			return {}

		return _FakeRequest(_execute)


class _FakeDrive:
	def __init__(self, list_pages, delete_behaviors=None):
		self.files_resource = _FakeFilesResource(list_pages, delete_behaviors)

	def files(self):
		return self.files_resource


class _DummySettings:
	def __init__(self, retention_days=30, backup_folder_id="BACKUP_ROOT", shared_drive_id=None):
		self.retention_days = retention_days
		self.backup_folder_id = backup_folder_id
		self.shared_drive_id = shared_drive_id


class _RunSettings(_DummySettings):
	def __init__(self):
		super().__init__()
		self.enable_backup = 1
		self.include_public_files = 1
		self.include_private_files = 1
		self.notification_email = ""
		self.notify_on_success = 0


def _google_datetime(value):
	return value.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _snapshot(folder_id, created_time):
	timestamp = created_time.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
	return {
		"id": folder_id,
		"name": f"{frappe.local.site}-backup-{timestamp}",
		"createdTime": _google_datetime(created_time),
		"mimeType": "application/vnd.google-apps.folder",
	}


def _make_http_error(status_code, message):
	response = _DummyHttpResponse(status_code)
	content = (f'{{"error":{{"code":{status_code},"message":"{message}"}}}}').encode()
	return HttpError(response, content, uri="https://www.googleapis.com/drive/v3/files/test")


def _patch_module_attr(module, attr_name, replacement, patched_attrs):
	patched_attrs.append((attr_name, getattr(module, attr_name)))
	setattr(module, attr_name, replacement)


class TestGoogleSharedDriveBackup(FrappeTestCase):
	def test_retention_deletes_old_snapshot(self):
		settings = _DummySettings(retention_days=30)
		old_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=45)
		drive = _FakeDrive(list_pages=[{"files": [_snapshot("old-1", old_time)], "nextPageToken": None}])

		result = backup_module._apply_retention_policy(drive, settings)

		self.assertEqual(result["deleted_count"], 1)
		self.assertEqual(result["already_missing_count"], 0)
		self.assertEqual(result["failed_count"], 0)
		self.assertEqual(drive.files_resource.delete_calls, ["old-1"])

	def test_retention_treats_404_as_already_missing(self):
		settings = _DummySettings(retention_days=30)
		old_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=45)
		drive = _FakeDrive(
			list_pages=[
				{
					"files": [
						_snapshot("old-404", old_time),
						_snapshot("old-2", old_time),
					],
					"nextPageToken": None,
				}
			],
			delete_behaviors={
				"old-404": _make_http_error(404, "File not found"),
			},
		)

		result = backup_module._apply_retention_policy(drive, settings)

		self.assertEqual(result["deleted_count"], 1)
		self.assertEqual(result["already_missing_count"], 1)
		self.assertEqual(result["failed_count"], 0)
		self.assertEqual(drive.files_resource.delete_calls, ["old-404", "old-2"])

	def test_retention_continues_after_non_404_failure(self):
		settings = _DummySettings(retention_days=30)
		old_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=45)
		drive = _FakeDrive(
			list_pages=[
				{
					"files": [
						_snapshot("old-fail", old_time),
						_snapshot("old-ok", old_time),
					],
					"nextPageToken": None,
				}
			],
			delete_behaviors={
				"old-fail": _make_http_error(400, "Bad request"),
			},
		)

		result = backup_module._apply_retention_policy(drive, settings)

		self.assertEqual(result["deleted_count"], 1)
		self.assertEqual(result["already_missing_count"], 0)
		self.assertEqual(result["failed_count"], 1)
		self.assertEqual(len(result["failures"]), 1)
		self.assertEqual(result["failures"][0]["folder_id"], "old-fail")
		self.assertEqual(drive.files_resource.delete_calls, ["old-fail", "old-ok"])

	def test_retention_skips_recent_snapshot(self):
		settings = _DummySettings(retention_days=30)
		recent_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=5)
		drive = _FakeDrive(
			list_pages=[{"files": [_snapshot("recent-1", recent_time)], "nextPageToken": None}]
		)

		result = backup_module._apply_retention_policy(drive, settings)

		self.assertEqual(result["deleted_count"], 0)
		self.assertEqual(result["already_missing_count"], 0)
		self.assertEqual(result["failed_count"], 0)
		self.assertEqual(drive.files_resource.delete_calls, [])

	def test_run_daily_backup_keeps_success_when_retention_crashes(self):
		settings = _RunSettings()
		notification_calls = []
		db_updates = []
		logged_errors = []
		patched_attrs = []

		original_set_single_value = frappe.db.set_single_value
		original_commit = frappe.db.commit
		original_log_error = frappe.log_error

		try:
			_patch_module_attr(backup_module, "_get_settings", lambda: settings, patched_attrs)
			_patch_module_attr(
				backup_module, "_validate_settings", lambda current_settings: None, patched_attrs
			)
			_patch_module_attr(backup_module, "_get_google_drive_service", lambda: object(), patched_attrs)
			_patch_module_attr(
				backup_module,
				"_validate_destination_folder",
				lambda drive, current_settings: None,
				patched_attrs,
			)
			_patch_module_attr(
				backup_module,
				"_create_snapshot_folder",
				lambda drive, current_settings: {"id": "snapshot-1", "name": "snapshot-1"},
				patched_attrs,
			)
			_patch_module_attr(
				backup_module, "_generate_backups", lambda current_settings: ["db.sql.gz"], patched_attrs
			)
			_patch_module_attr(
				backup_module,
				"_upload_file_to_shared_drive",
				lambda drive, settings, backup_path, parent_folder_id: {"id": "file-1"},
				patched_attrs,
			)
			_patch_module_attr(
				backup_module,
				"_apply_retention_policy",
				lambda drive, current_settings: (_ for _ in ()).throw(RuntimeError("retention failure")),
				patched_attrs,
			)
			_patch_module_attr(
				backup_module,
				"_send_notification",
				lambda current_settings, success, message: notification_calls.append(
					{"success": success, "message": message}
				),
				patched_attrs,
			)

			frappe.db.set_single_value = lambda doctype, values: db_updates.append((doctype, values))
			frappe.db.commit = lambda: None
			frappe.log_error = lambda *args, **kwargs: logged_errors.append((args, kwargs))

			backup_module.run_daily_backup()
		finally:
			for attr_name, original in reversed(patched_attrs):
				setattr(backup_module, attr_name, original)

			frappe.db.set_single_value = original_set_single_value
			frappe.db.commit = original_commit
			frappe.log_error = original_log_error

		self.assertEqual(len(notification_calls), 1)
		self.assertEqual(notification_calls[0]["success"], True)
		self.assertIn("Retencao nao foi concluida", notification_calls[0]["message"])
		self.assertEqual(len(db_updates), 1)
		self.assertEqual(db_updates[0][0], backup_module.SETTINGS_DOCTYPE)
		self.assertEqual(db_updates[0][1]["last_error"], "")
		self.assertEqual(len(logged_errors), 1)
