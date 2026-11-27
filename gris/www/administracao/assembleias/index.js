// Lista de assembleias: datas por extenso nos cards e o dialog "Nova assembleia".
(function () {
	const A = window.grisAssembleias;
	if (!A) return;

	const dialog = document.getElementById("dialog-nova-assembleia");
	A.calendariosPorCimaDoDialog(dialog);

	document.querySelectorAll(".asm-card__dia").forEach((el) => {
		const iso = el.dataset.data;
		el.textContent = `${A.dataBR(iso)} · ${A.diaDaSemana(iso)}`;
	});
	document.querySelectorAll("[data-prazo]").forEach((el) => {
		el.title = `Publicar até ${A.dataBR(el.dataset.prazo)}`;
		el.textContent = `Publicar edital até ${A.dataBR(el.dataset.prazo)}`;
	});

	document.addEventListener("click", (evento) => {
		if (evento.target.closest("[data-nova-assembleia]") && dialog) {
			dialog.showModal();
		}
	});

	document.getElementById("btn-criar-assembleia")?.addEventListener("click", async (evento) => {
		const botao = evento.currentTarget;
		const dados = {
			data: A.valorDaData("nova-data"),
			tipo: A.valorDoSelect("nova-tipo") || "Ordinária",
			hora_primeira_convocacao: document.getElementById("nova-hora").value,
			local: document.getElementById("nova-local").value.trim(),
		};
		if (!dados.data || !dados.hora_primeira_convocacao || !dados.local) {
			A.toast("error", "Preencha a data, o horário e o local.");
			return;
		}
		botao.disabled = true;
		try {
			const resposta = await A.chamar("endpoints.criar_assembleia", {
				payload: JSON.stringify(dados),
			});
			window.location.href = resposta.url;
		} catch (erro) {
			A.toast("error", erro.message);
			botao.disabled = false;
		}
	});
})();
