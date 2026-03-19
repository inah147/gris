function get_drive_map(frm) {
	const driveMap = {};
	(frm.doc.drives_compartilhados || []).forEach((row) => {
		if (!row.ativo || !row.nome_drive || !row.drive_id) {
			return;
		}
		driveMap[row.nome_drive.trim()] = row.drive_id.trim();
	});
	return driveMap;
}

function set_manual_drive_options(frm) {
	const driveMap = get_drive_map(frm);
	const options = Object.keys(driveMap).join("\n");

	frm.fields_dict.concessoes_manuais.grid.update_docfield_property("drive", "options", options);
	frm.refresh_field("concessoes_manuais");

	(frm.doc.concessoes_manuais || []).forEach((row) => {
		if (!row.drive || !driveMap[row.drive]) {
			row.drive_id = "";
			return;
		}
		row.drive_id = driveMap[row.drive];
	});
	frm.refresh_field("concessoes_manuais");
}

frappe.ui.form.on("Configuracoes Google Workspace", {
	refresh(frm) {
		set_manual_drive_options(frm);
	},
	validate(frm) {
		set_manual_drive_options(frm);
	},
	drives_compartilhados_add(frm) {
		set_manual_drive_options(frm);
	},
	drives_compartilhados_remove(frm) {
		set_manual_drive_options(frm);
	},
});

frappe.ui.form.on("Drives Compartilhados Workspace", {
	drive_id(frm) {
		set_manual_drive_options(frm);
	},
	ativo(frm) {
		set_manual_drive_options(frm);
	},
});

frappe.ui.form.on("Concessoes Manuais Workspace", {
	associado(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.associado) {
			frappe.model.set_value(cdt, cdn, "email_institucional", "");
			return;
		}

		frappe.db.get_value("Associado", row.associado, "id_escoteiros").then((result) => {
			const email = (result.message && result.message.id_escoteiros) || "";
			frappe.model.set_value(cdt, cdn, "email_institucional", email);
		});
	},
	drive(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const driveMap = get_drive_map(frm);
		const driveId = row.drive ? driveMap[row.drive] || "" : "";
		frappe.model.set_value(cdt, cdn, "drive_id", driveId);
	},
});
