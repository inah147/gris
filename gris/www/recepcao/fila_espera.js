// Fila de Espera da Recepção — interações cliente
// Usa exclusivamente o design system Basecoat (<dialog> HTML5 + alert + badge).
// O dialog de vagas (com o gráfico de previsão) é compartilhado com a visão geral:
// ver public/js/vagas_do_ramo.js.

(function () {
	let currentFilaId = null;
	let currentAssociadoId = null;
	let currentAssociadoNome = "";

	// ---------- Helpers de dialog --------------------------------------------

	function openDialog(id) {
		const el = document.getElementById(id);
		if (!el || typeof el.showModal !== "function" || el.open) return;
		try {
			el.showModal();
		} catch (err) {
			console.error(`Falha ao abrir dialog "${id}":`, err);
			frappe.show_alert({
				message: "Não foi possível abrir o modal. Recarregue a página.",
				indicator: "red",
			});
		}
	}

	function closeDialog(id) {
		const el = document.getElementById(id);
		if (el && el.open) el.close();
	}

	// ---------- Modal de detalhes da fila ------------------------------------

	function openFilaModal(card) {
		currentFilaId = card.dataset.id;
		currentAssociadoId = card.dataset.associado;
		currentAssociadoNome = card.dataset.nome || "este associado";

		document.getElementById("modalAssociadoNome").textContent = card.dataset.nome || "";
		document.getElementById("modalResponsavelNome").textContent =
			card.dataset.responsavel || "";
		document.getElementById("modalPosicao").textContent = "#" + (card.dataset.posicao || "");
		document.getElementById("modalPrevisao").textContent =
			card.dataset.previsao || "Sem previsão";
		document.getElementById("modalDataInclusao").textContent = card.dataset.dataInclusao || "";

		openDialog("modalFilaEspera");
	}

	function abrirFicha() {
		if (currentAssociadoId) {
			window.location.href = `/recepcao/ficha_registro?name=${encodeURIComponent(
				currentAssociadoId
			)}`;
		}
	}

	// ---------- Modal de confirmação de chamada ------------------------------

	function abrirConfirmarChamada() {
		if (!currentFilaId) return;
		document.getElementById("modalChamadaNome").textContent = currentAssociadoNome;
		closeDialog("modalFilaEspera");
		openDialog("modalConfirmarChamada");
	}

	function cancelarChamada() {
		closeDialog("modalConfirmarChamada");
		// Reabre o modal anterior caso ainda haja contexto.
		if (currentFilaId) openDialog("modalFilaEspera");
	}

	function confirmarChamada() {
		if (!currentFilaId) return;
		// Fecha antes de chamar o servidor: com um <dialog> aberto via showModal()
		// o restante da página fica inerte e mensagens do Frappe não apareceriam.
		closeDialog("modalConfirmarChamada");
		frappe.call({
			method: "gris.www.recepcao.fila_espera.chamar_associado",
			args: { fila_id: currentFilaId },
			freeze: true,
			freeze_message: "Chamando associado...",
			callback: function (r) {
				if (r.exc) return;
				frappe.show_alert({
					message: "Associado chamado com sucesso",
					indicator: "green",
				});
				setTimeout(() => window.location.reload(), 800);
			},
			error: function () {
				frappe.show_alert({
					message: "Não foi possível chamar o associado",
					indicator: "red",
				});
			},
		});
	}

	// ---------- Modal de confirmação de desistência --------------------------

	function abrirConfirmarDesistencia() {
		if (!currentFilaId) return;
		closeDialog("modalFilaEspera");
		openDialog("modalConfirmarDesistencia");
	}

	function cancelarDesistencia() {
		closeDialog("modalConfirmarDesistencia");
		// Reabre o modal anterior caso ainda haja contexto.
		if (currentFilaId) openDialog("modalFilaEspera");
	}

	function confirmarDesistencia() {
		if (!currentFilaId) return;
		// Mesmo motivo de confirmarChamada: fechar o dialog antes da chamada.
		closeDialog("modalConfirmarDesistencia");
		frappe.call({
			method: "gris.www.recepcao.fila_espera.registrar_desistencia",
			args: { fila_id: currentFilaId },
			freeze: true,
			freeze_message: "Registrando desistência...",
			callback: function (r) {
				if (r.exc) return;
				frappe.show_alert({ message: "Desistência registrada", indicator: "green" });
				setTimeout(() => window.location.reload(), 800);
			},
			error: function () {
				frappe.show_alert({
					message: "Não foi possível registrar a desistência",
					indicator: "red",
				});
			},
		});
	}

	// ---------- Bootstrap -----------------------------------------------------

	frappe.ready(function () {
		// Cards do Kanban → modal de detalhes
		document.querySelectorAll(".kanban-card").forEach((card) => {
			card.addEventListener("click", () => openFilaModal(card));
		});

		// Botão de vagas no header de cada coluna → dialog compartilhado
		document.querySelectorAll(".kanban-column__vagas").forEach((btn) => {
			btn.addEventListener("click", () => window.grisVagasDoRamo.abrir(btn.dataset.ramo));
		});

		// Ações do modal de fila de espera
		document
			.getElementById("btnChamarAssociado")
			?.addEventListener("click", abrirConfirmarChamada);
		document.getElementById("btnAbrirFicha")?.addEventListener("click", abrirFicha);
		document
			.getElementById("btnRegistrarDesistencia")
			?.addEventListener("click", abrirConfirmarDesistencia);

		// Ações dos modais de confirmação
		document.getElementById("btnCancelarChamada")?.addEventListener("click", cancelarChamada);
		document
			.getElementById("btnConfirmarChamada")
			?.addEventListener("click", confirmarChamada);
		document
			.getElementById("btnCancelarDesistencia")
			?.addEventListener("click", cancelarDesistencia);
		document
			.getElementById("btnConfirmarDesistencia")
			?.addEventListener("click", confirmarDesistencia);

		// Botão "Fechar" dos dialogs (atributo data-dialog-close)
		document.addEventListener("click", (event) => {
			const closer = event.target.closest("[data-dialog-close]");
			if (closer) {
				const dlg = closer.closest("dialog");
				if (dlg && dlg.open) dlg.close();
			}
		});
	});
})();
