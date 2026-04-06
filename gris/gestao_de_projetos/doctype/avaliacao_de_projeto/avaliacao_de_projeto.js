function set_reviewer_options(frm, reviewerNames) {
  const options = ["", ...reviewerNames].join("\n");
  frappe.meta.get_docfield("Avaliacao Individual Projeto", "avaliador", frm.doc.name).options = options;
  frm.refresh_field("avaliacoes_individuais");
}

async function refresh_reviewer_options(frm) {
  if (!frm.doc.projeto) {
    set_reviewer_options(frm, []);
    return;
  }

  try {
    const response = await frappe.call({
      method: "gris.gestao_de_projetos.doctype.avaliacao_de_projeto.avaliacao_de_projeto.get_avaliadores_permitidos",
      args: { projeto: frm.doc.projeto },
    });
    set_reviewer_options(frm, response.message || []);
  } catch (error) {
    frappe.msgprint(__("Nao foi possivel carregar avaliadores permitidos."));
  }
}

frappe.ui.form.on("Avaliacao de Projeto", {
  refresh(frm) {
    refresh_reviewer_options(frm);
  },
  projeto(frm) {
    refresh_reviewer_options(frm);
  },
});
