let currentFilaId = null;
let currentAssociadoId = null;

frappe.ready(function () {
	$(".kanban-card").on("click", function () {
		const id = $(this).data("id");
		const associado = $(this).data("associado");
		const nome = $(this).data("nome");
		const responsavel = $(this).data("responsavel");
		const posicao = $(this).data("posicao");
		const previsao = $(this).data("previsao");
		const dataInclusao = $(this).data("data-inclusao");

		openModal(id, associado, nome, responsavel, posicao, previsao, dataInclusao);
	});

	$("[data-dismiss-modal]").on("click", closeModal);
	$(document).on("click", ".modal-backdrop", function (e) {
		if ($(e.target).hasClass("modal-backdrop")) {
			closeModal();
		}
	});
});

function openModal(id, associado, nome, responsavel, posicao, previsao, dataInclusao) {
	currentFilaId = id;
	currentAssociadoId = associado;

	$("#modalAssociadoNome").text(nome);
	$("#modalResponsavelNome").text(responsavel);
	$("#modalPosicao").text("#" + posicao);
	$("#modalPrevisao").text(previsao || "Sem previsão");
	$("#modalDataInclusao").text(dataInclusao);

	const modal = $("#modalFilaEspera");
	modal.removeClass("d-none");
	modal.addClass("show");
	$("body").addClass("modal-open");

	if ($(".modal-backdrop").length === 0) {
		$('<div class="modal-backdrop fade show"></div>').appendTo(document.body);
	}
}

function closeModal() {
	$(".modal-modern").removeClass("show").addClass("d-none");
	$("body").removeClass("modal-open");
	$(".modal-backdrop").remove();
	currentFilaId = null;
	currentAssociadoId = null;
}

function openFicha() {
	if (currentAssociadoId) {
		window.location.href = `/recepcao/ficha_registro?name=${currentAssociadoId}`;
	}
}

function chamarAssociado() {
	if (!currentFilaId) return;
	frappe.confirm(
		"Tem certeza que deseja chamar este associado? Ele sairá da fila de espera.",
		() => {
			frappe.call({
				method: "gris.www.recepcao.fila_espera.chamar_associado",
				args: { fila_id: currentFilaId },
				callback: function (r) {
					if (!r.exc) {
						frappe.show_alert({
							message: "Associado chamado com sucesso",
							indicator: "green",
						});
						closeModal();
						setTimeout(() => window.location.reload(), 1000);
					}
				},
			});
		}
	);
}

function registrarDesistencia() {
	if (!currentFilaId) return;

	// Close current modal
	$("#modalFilaEspera").removeClass("show").addClass("d-none");

	// Open confirmation modal
	const modal = $("#modalConfirmarDesistencia");
	modal.removeClass("d-none");
	modal.addClass("show");

	if ($(".modal-backdrop").length === 0) {
		$('<div class="modal-backdrop fade show"></div>').appendTo(document.body);
	}
}

function closeConfirmarDesistencia() {
	const modal = $("#modalConfirmarDesistencia");
	modal.removeClass("show");
	modal.addClass("d-none");

	// Reopen previous modal
	$("#modalFilaEspera").removeClass("d-none").addClass("show");
}

function confirmarDesistencia() {
	frappe.call({
		method: "gris.www.recepcao.fila_espera.registrar_desistencia",
		args: {
			fila_id: currentFilaId,
		},
		callback: function (r) {
			if (!r.exc) {
				frappe.show_alert({ message: "Desistência registrada", indicator: "green" });
				$("#modalConfirmarDesistencia").removeClass("show").addClass("d-none");
				setTimeout(() => window.location.reload(), 1000);
			}
		},
	});
}

function openVagasModal(element) {
	const ramo = $(element).data("ramo");
	const limite = $(element).data("limite");
	const ativos = $(element).data("ativos");
	const novos = $(element).data("novos");
	const saindo = $(element).data("saindo");
	const disponiveis = $(element).data("disponiveis");

	const chartLabels = $(element).data("chart-labels");
	const chartValues = $(element).data("chart-values");

	$("#modalVagasRamo").text(ramo);
	$("#vagasLimite").text(limite);
	$("#vagasAtivos").text(ativos);
	$("#vagasNovos").text(novos);
	$("#vagasSaindo").text(saindo);
	$("#vagasDisponiveis").text(disponiveis);

	const modal = $("#modalVagas");
	modal.removeClass("d-none");
	modal.addClass("show");
	$("body").addClass("modal-open");

	if ($(".modal-backdrop").length === 0) {
		$('<div class="modal-backdrop fade show"></div>').appendTo(document.body);
	}

	if (chartLabels && chartValues) {
		// Clear previous chart if any
		$("#vagasChart").empty();

		// Determine Chart constructor
		let ChartConstructor = frappe.Chart;
		if (!ChartConstructor && window["frappe-charts"]) {
			ChartConstructor = window["frappe-charts"].Chart;
		}

		if (ChartConstructor) {
			new ChartConstructor("#vagasChart", {
				data: {
					labels: chartLabels,
					datasets: [
						{
							name: "Vagas",
							chartType: "line",
							values: chartValues,
						},
					],
				},
				type: "line",
				height: 250,
				colors: ["#5e64ff"],
				lineOptions: {
					regionFill: 1,
					hideDots: 0,
				},
				axisOptions: {
					xIsSeries: true,
				},
			});
		} else {
			console.error("Frappe Charts library not found.");
		}
	}
}

window.openFicha = openFicha;
window.chamarAssociado = chamarAssociado;
window.registrarDesistencia = registrarDesistencia;
window.closeConfirmarDesistencia = closeConfirmarDesistencia;
window.confirmarDesistencia = confirmarDesistencia;
window.openVagasModal = openVagasModal;
