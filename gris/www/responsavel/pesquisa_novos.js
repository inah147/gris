frappe.ready(function () {
	const form = document.getElementById("survey-form");
	if (!form) return;
	if (form.dataset.readOnly === "true") return;

	function showToast({ title, description, category }) {
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: { config: { title, description, category } },
			})
		);
	}

	form.addEventListener("submit", function (e) {
		e.preventDefault();

		const formData = new FormData(form);
		const data = {};
		for (const [key, value] of formData.entries()) {
			data[key] = value;
		}

		if (
			!data.como_conheceu_movimento ||
			!data.como_voce_conheceu_grupo ||
			!data.nps_recepcao
		) {
			showToast({
				title: "Campos obrigatórios",
				description: "Preencha as duas seleções e a nota NPS antes de enviar.",
				category: "warning",
			});
			return;
		}

		frappe.call({
			method: "gris.www.responsavel.pesquisa_novos.submit_survey",
			args: { data: JSON.stringify(data) },
			freeze: true,
			freeze_message: "Enviando...",
			callback: function (r) {
				if (r.exc) return;
				showToast({
					title: "Pesquisa enviada",
					description: r.message || "Obrigado pelo retorno!",
					category: "success",
				});
				setTimeout(() => window.location.reload(), 1500);
			},
		});
	});
});
