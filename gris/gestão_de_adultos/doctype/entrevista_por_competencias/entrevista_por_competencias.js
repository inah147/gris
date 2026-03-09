frappe.ui.form.on("Entrevista por Competencias", {
	async refresh(frm) {
		try {
			const response = await frappe.call({
				method: "gris.api.gestao_adultos.get_opcoes_respostas_por_pergunta",
			});

			const optionsByFieldname = response.message || {};
			Object.keys(optionsByFieldname).forEach((fieldname) => {
				const field = frm.fields_dict[fieldname];
				if (!field) {
					return;
				}

				field.df.options = ["", ...optionsByFieldname[fieldname]].join("\n");
				frm.refresh_field(fieldname);
			});
		} catch (error) {
			console.warn("Não foi possível carregar as opções da entrevista.", error);
		}
	},
});
