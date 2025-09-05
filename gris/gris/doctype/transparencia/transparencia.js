// Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
// For license information, please see license.txt


function update_semestre_referencia_properties(frm) {
    const show = frm.doc.tipo_arquivo === "Parecer semestral da comissão fiscal";
    frm.set_df_property("semestre_referencia", "hidden", !show);
    frm.set_df_property("semestre_referencia", "reqd", show);
}

frappe.ui.form.on("Transparencia", {
    tipo_arquivo(frm) {
        update_semestre_referencia_properties(frm);
    },
    refresh(frm) {
        update_semestre_referencia_properties(frm);
    },
});
