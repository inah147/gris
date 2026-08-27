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

frappe.ui.form.on("Projeto", {
	refresh(frm) {
		frm.set_query("padrinho_associado", () => ({
			filters: {
				categoria: ["not like", "Benefici%"],
			},
		}));
	},
});

frappe.ui.form.on("Envolvido no Projeto", {
	tipo_pessoa(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.tipo_pessoa === "Associado") {
			set_child_value(frm, cdt, cdn, {
				responsavel: "",
			});
			return;
		}

		if (row.tipo_pessoa === "Responsavel") {
			set_child_value(frm, cdt, cdn, {
				associado: "",
			});
			return;
		}

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
		fill_person_contact(frm, cdt, cdn, "Associado", row.associado);
	},
	responsavel(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.tipo_pessoa !== "Responsavel") {
			return;
		}
		fill_person_contact(frm, cdt, cdn, "Responsavel", row.responsavel);
	},
});
