function set_child_value(frm, cdt, cdn, values) {
  const row = locals[cdt][cdn];
  Object.keys(values).forEach((key) => {
    frappe.model.set_value(cdt, cdn, key, values[key]);
  });
  frm.refresh_field(row.parentfield);
}

async function fill_person_contact(frm, cdt, cdn, doctypeName, docname) {
  if (!docname) {
    return;
  }

  try {
    const response = await frappe.call({
      method: "gris.gestao_de_projetos.doctype.projeto.projeto.get_contato_pessoa",
      args: {
        doctype_name: doctypeName,
        docname,
      },
    });

    if (!response.message) {
      return;
    }

    set_child_value(frm, cdt, cdn, {
      nome: response.message.nome || "",
      email: response.message.email || "",
      telefone: response.message.telefone || "",
    });
  } catch (error) {
    frappe.msgprint(__("Nao foi possivel carregar contato automaticamente."));
  }
}

function team_member_names(doc) {
  return (doc.equipe_de_interesse || [])
    .map((row) => row.nome)
    .filter((name) => !!name);
}

function update_dynamic_select_options(frm) {
  const responsavelField = frappe.meta.get_docfield("Gestao de Tarefas", "responsavel", frm.doc.name);
  if (!responsavelField) {
    return;
  }

  const taskOptions = ["", ...team_member_names(frm.doc)].join("\n");
  responsavelField.options = taskOptions;

  frm.refresh_field("tarefas");
}

frappe.ui.form.on("Projeto", {
  refresh(frm) {
    frm.set_query("padrinho_associado", () => ({
      filters: {
        categoria: ["not like", "Benefici%"],
      },
    }));

    update_dynamic_select_options(frm);
  },
  equipe_de_interesse_add(frm) {
    update_dynamic_select_options(frm);
  },
  equipe_de_interesse_remove(frm) {
    update_dynamic_select_options(frm);
  },
  padrinho_associado(frm) {
    update_dynamic_select_options(frm);
  },
  padrinho_responsavel(frm) {
    update_dynamic_select_options(frm);
  },
});

frappe.ui.form.on("Outro Envolvido Projeto", {
  associado(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    fill_person_contact(frm, cdt, cdn, "Associado", row.associado);
  },
});

frappe.ui.form.on("Equipe de Interesse Projeto", {
  tipo_pessoa(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (row.tipo_pessoa === "Outro") {
      set_child_value(frm, cdt, cdn, {
        associado: "",
        responsavel: "",
      });
    }
  },
  associado(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (row.tipo_pessoa !== "Associado") {
      return;
    }
    fill_person_contact(frm, cdt, cdn, "Associado", row.associado).then(() => {
      update_dynamic_select_options(frm);
    });
  },
  responsavel(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (row.tipo_pessoa !== "Responsavel") {
      return;
    }
    fill_person_contact(frm, cdt, cdn, "Responsavel", row.responsavel).then(() => {
      update_dynamic_select_options(frm);
    });
  },
  nome(frm) {
    update_dynamic_select_options(frm);
  },
});
