(function () {
	function openCadastroModal() {
		const modal = document.getElementById("projetosCadastroModal");
		if (!modal) {
			return;
		}
		modal.classList.remove("d-none");
		document.body.classList.add("modal-open");
	}

	function closeCadastroModal() {
		const modal = document.getElementById("projetosCadastroModal");
		if (!modal) {
			return;
		}
		modal.classList.add("d-none");
		document.body.classList.remove("modal-open");
	}

	document.addEventListener("DOMContentLoaded", function () {
		document.querySelectorAll("[data-open-cadastro-modal]").forEach((btn) => {
			btn.addEventListener("click", function (event) {
				event.preventDefault();
				openCadastroModal();
			});
		});

		document.querySelectorAll("[data-close-cadastro-modal]").forEach((btn) => {
			btn.addEventListener("click", closeCadastroModal);
		});

		const modal = document.getElementById("projetosCadastroModal");
		if (modal) {
			modal.addEventListener("click", function (event) {
				if (event.target === modal) {
					closeCadastroModal();
				}
			});
		}

		const params = new URLSearchParams(window.location.search);
		if (params.get("acao") === "cadastrar") {
			openCadastroModal();
		}
	});
})();
