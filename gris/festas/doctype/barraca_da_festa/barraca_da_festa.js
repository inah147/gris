// Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
// For license information, please see license.txt

const FESTA_CONTATO_METHOD = "gris.utils.contato.get_contato_pessoa";

async function fetch_contato(doctype_name, docname) {
	if (!docname) return null;
	const r = await frappe.call({
		method: FESTA_CONTATO_METHOD,
		args: { doctype_name: doctype_name, docname: docname },
	});
	return r && r.message ? r.message : null;
}

function clear_coord_fields(frm) {
	frm.set_value("nome_coord", "");
	frm.set_value("email_coord", "");
	frm.set_value("telefone_coord", "");
}

async function fill_barraca_coord_from_link(frm, doctype_name, docname) {
	const data = await fetch_contato(doctype_name, docname);
	if (!data) return;
	frm.set_value("nome_coord", data.nome || "");
	frm.set_value("email_coord", data.email || "");
	frm.set_value("telefone_coord", data.telefone || "");
}

frappe.ui.form.on("Barraca da Festa", {
	tipo_coord(frm) {
		if (frm.doc.tipo_coord === "Associado") {
			frm.set_value("responsavel_coord", "");
		} else if (frm.doc.tipo_coord === "Responsavel") {
			frm.set_value("associado_coord", "");
		} else {
			frm.set_value("associado_coord", "");
			frm.set_value("responsavel_coord", "");
		}
		clear_coord_fields(frm);
	},
	associado_coord(frm) {
		if (frm.doc.tipo_coord === "Associado" && frm.doc.associado_coord) {
			fill_barraca_coord_from_link(frm, "Associado", frm.doc.associado_coord);
		}
	},
	responsavel_coord(frm) {
		if (frm.doc.tipo_coord === "Responsavel" && frm.doc.responsavel_coord) {
			fill_barraca_coord_from_link(frm, "Responsavel", frm.doc.responsavel_coord);
		}
	},
});

// Handlers compartilhados para Membro Equipe Festa
function clear_membro_contato(frm, cdt, cdn) {
	frappe.model.set_value(cdt, cdn, "nome", "");
	frappe.model.set_value(cdt, cdn, "email", "");
	frappe.model.set_value(cdt, cdn, "telefone", "");
}

async function fill_membro_from_link(frm, cdt, cdn, doctype_name, docname) {
	const data = await fetch_contato(doctype_name, docname);
	if (!data) return;
	frappe.model.set_value(cdt, cdn, "nome", data.nome || "");
	frappe.model.set_value(cdt, cdn, "email", data.email || "");
	frappe.model.set_value(cdt, cdn, "telefone", data.telefone || "");
}

frappe.ui.form.on("Membro Equipe Festa", {
	tipo_pessoa(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.tipo_pessoa === "Associado") {
			frappe.model.set_value(cdt, cdn, "responsavel", "");
		} else if (row.tipo_pessoa === "Responsavel") {
			frappe.model.set_value(cdt, cdn, "associado", "");
		} else {
			frappe.model.set_value(cdt, cdn, "associado", "");
			frappe.model.set_value(cdt, cdn, "responsavel", "");
		}
		clear_membro_contato(frm, cdt, cdn);
	},
	associado(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.tipo_pessoa === "Associado" && row.associado) {
			fill_membro_from_link(frm, cdt, cdn, "Associado", row.associado);
		}
	},
	responsavel(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.tipo_pessoa === "Responsavel" && row.responsavel) {
			fill_membro_from_link(frm, cdt, cdn, "Responsavel", row.responsavel);
		}
	},
});
