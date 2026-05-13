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

function clear_coord_geral(frm) {
	frm.set_value("nome_coord_geral", "");
	frm.set_value("email_coord_geral", "");
	frm.set_value("telefone_coord_geral", "");
}

async function fill_coord_geral(frm, doctype_name, docname) {
	const data = await fetch_contato(doctype_name, docname);
	if (!data) return;
	frm.set_value("nome_coord_geral", data.nome || "");
	frm.set_value("email_coord_geral", data.email || "");
	frm.set_value("telefone_coord_geral", data.telefone || "");
}

frappe.ui.form.on("Festa", {
	tipo_coord_geral(frm) {
		if (frm.doc.tipo_coord_geral === "Associado") {
			frm.set_value("responsavel_coord_geral", "");
		} else if (frm.doc.tipo_coord_geral === "Responsavel") {
			frm.set_value("associado_coord_geral", "");
		}
		clear_coord_geral(frm);
	},
	associado_coord_geral(frm) {
		if (frm.doc.tipo_coord_geral === "Associado" && frm.doc.associado_coord_geral) {
			fill_coord_geral(frm, "Associado", frm.doc.associado_coord_geral);
		}
	},
	responsavel_coord_geral(frm) {
		if (frm.doc.tipo_coord_geral === "Responsavel" && frm.doc.responsavel_coord_geral) {
			fill_coord_geral(frm, "Responsavel", frm.doc.responsavel_coord_geral);
		}
	},
});
