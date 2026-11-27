// Página da assembleia.
(function () {
	const A = window.grisAssembleias;
	const raiz = document.querySelector(".asm-assembleia");
	if (!A || !raiz) return;

	const name = raiz.dataset.name;

	// ── Exclusão (RF-02) ──
	const dialogExcluir = document.getElementById("dialog-excluir-assembleia");
	document
		.querySelector("[data-excluir-assembleia]")
		?.addEventListener("click", () => dialogExcluir?.showModal());
	document
		.getElementById("btn-confirmar-exclusao")
		?.addEventListener("click", async (evento) => {
			const botao = evento.currentTarget;
			botao.disabled = true;
			try {
				await A.chamar("endpoints.excluir_assembleia", { name });
				window.location.href = "/administracao/assembleias";
			} catch (erro) {
				A.toast("error", erro.message);
				botao.disabled = false;
			}
		});
})();
