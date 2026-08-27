(function () {
	"use strict";

	var SUBMIT_METHOD =
		"gris.festas.doctype.avaliacao_festa.avaliacao_festa.submeter_avaliacao_individual_festa";

	function getToken() {
		return (document.getElementById("avaliacaoToken") || {}).value || "";
	}

	function showFormAlert(message, type) {
		var el = document.getElementById("avaliacaoAlert");
		if (!el) return;

		el.className = "alert " + (type === "error" ? "alert-destructive" : "alert-success");
		el.setAttribute("role", type === "error" ? "alert" : "status");
		el.setAttribute("aria-live", type === "error" ? "assertive" : "polite");

		var section = document.createElement("section");
		section.textContent = message;
		el.replaceChildren(section);
		el.removeAttribute("hidden");
		el.scrollIntoView({ behavior: "smooth", block: "center" });
	}

	function hideFormAlert() {
		var el = document.getElementById("avaliacaoAlert");
		if (!el) return;
		el.setAttribute("hidden", "");
		el.replaceChildren();
	}

	function getSelectedRadio(name) {
		var radios = document.querySelectorAll('input[name="' + name + '"]');
		for (var i = 0; i < radios.length; i++) {
			if (radios[i].checked) return radios[i].value;
		}
		return null;
	}

	function showState(stateId) {
		var states = document.querySelectorAll(".avaliacao-state");
		for (var i = 0; i < states.length; i++) {
			states[i].classList.add("d-none");
		}
		var target = document.getElementById(stateId);
		if (target) target.classList.remove("d-none");
	}

	function setSubmitLoading(button, isLoading) {
		if (!button) return;

		if (!button.dataset.defaultLabel) {
			button.dataset.defaultLabel = button.textContent.trim();
		}

		button.disabled = isLoading;
		button.toggleAttribute("aria-busy", isLoading);
		button.textContent = isLoading ? "Enviando..." : button.dataset.defaultLabel;
	}

	function handleSubmit(event) {
		event.preventDefault();
		hideFormAlert();

		var token = getToken();
		if (!token) {
			showFormAlert("Token de avaliação não encontrado.", "error");
			return;
		}

		var resultado = getSelectedRadio("resultado_festa");
		var satisfacao = getSelectedRadio("satisfacao_colaboracao");
		var muitoBom = (document.getElementById("muito_bom") || {}).value || "";
		var pontosMelhoria = (document.getElementById("pontos_melhoria") || {}).value || "";

		if (resultado === null) {
			showFormAlert("Por favor, avalie o resultado da festa (nota de 0 a 10).", "error");
			return;
		}
		if (satisfacao === null) {
			showFormAlert(
				"Por favor, indique sua satisfação em colaborar (nota de 0 a 10).",
				"error"
			);
			return;
		}
		if (!muitoBom.trim()) {
			showFormAlert("Por favor, descreva o que foi muito bom na festa.", "error");
			return;
		}
		if (!pontosMelhoria.trim()) {
			showFormAlert("Por favor, descreva os pontos de melhoria.", "error");
			return;
		}

		var btn = document.getElementById("btnSubmitAvaliacao");
		setSubmitLoading(btn, true);

		frappe.call({
			method: SUBMIT_METHOD,
			args: {
				token: token,
				resultado_festa: resultado,
				satisfacao_colaboracao: satisfacao,
				muito_bom: muitoBom.trim(),
				pontos_melhoria: pontosMelhoria.trim(),
			},
			callback: function (r) {
				if (r && r.message && r.message.ok) {
					showState("stateSuccess");
				} else {
					showFormAlert("Erro ao enviar avaliação. Tente novamente.", "error");
					setSubmitLoading(btn, false);
				}
			},
			error: function () {
				showFormAlert("Erro de comunicação com o servidor. Tente novamente.", "error");
				setSubmitLoading(btn, false);
			},
		});
	}

	document.addEventListener("DOMContentLoaded", function () {
		var form = document.getElementById("avaliacaoForm");
		if (form) {
			form.addEventListener("submit", handleSubmit);
		}
	});
})();
