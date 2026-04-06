(function () {
    "use strict";

    var SUBMIT_METHOD =
        "gris.gestao_de_projetos.doctype.avaliacao_de_projeto.avaliacao_de_projeto.submeter_avaliacao_individual";

    function getToken() {
        return (document.getElementById("avaliacaoToken") || {}).value || "";
    }

    function showFormAlert(message, type) {
        var el = document.getElementById("avaliacaoAlert");
        if (!el) return;
        el.className = "alert-modern";
        el.classList.add(type === "error" ? "alert-modern--error" : "alert-modern--success");
        el.textContent = message;
        el.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    function hideFormAlert() {
        var el = document.getElementById("avaliacaoAlert");
        if (!el) return;
        el.className = "alert-modern d-none";
        el.textContent = "";
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

    function handleSubmit(event) {
        event.preventDefault();
        hideFormAlert();

        var token = getToken();
        if (!token) {
            showFormAlert("Token de avaliação não encontrado.", "error");
            return;
        }

        var resultado = getSelectedRadio("resultado_projeto");
        var satisfacao = getSelectedRadio("satisfacao_colaboracao");
        var objetivos = (document.getElementById("objetivos_atingidos") || {}).value || "";
        var muitoBom = (document.getElementById("muito_bom") || {}).value || "";
        var pontosMelhoria = (document.getElementById("pontos_melhoria") || {}).value || "";

        if (resultado === null) {
            showFormAlert("Por favor, avalie o resultado do projeto (nota de 0 a 10).", "error");
            return;
        }
        if (satisfacao === null) {
            showFormAlert("Por favor, indique sua satisfação em colaborar (nota de 0 a 10).", "error");
            return;
        }
        if (!objetivos.trim()) {
            showFormAlert("Por favor, descreva se o projeto atingiu os objetivos.", "error");
            return;
        }
        if (!muitoBom.trim()) {
            showFormAlert("Por favor, descreva o que foi muito bom no projeto.", "error");
            return;
        }
        if (!pontosMelhoria.trim()) {
            showFormAlert("Por favor, descreva os pontos de melhoria.", "error");
            return;
        }

        var btn = document.getElementById("btnSubmitAvaliacao");
        if (btn) {
            btn.disabled = true;
            btn.textContent = "Enviando...";
        }

        frappe.call({
            method: SUBMIT_METHOD,
            args: {
                token: token,
                resultado_projeto: resultado,
                satisfacao_colaboracao: satisfacao,
                objetivos_atingidos: objetivos.trim(),
                muito_bom: muitoBom.trim(),
                pontos_melhoria: pontosMelhoria.trim(),
            },
            callback: function (r) {
                if (r && r.message && r.message.ok) {
                    showState("stateSuccess");
                } else {
                    showFormAlert("Erro ao enviar avaliação. Tente novamente.", "error");
                    if (btn) {
                        btn.disabled = false;
                        btn.textContent = "Enviar avaliação";
                    }
                }
            },
            error: function () {
                showFormAlert("Erro de comunicação com o servidor. Tente novamente.", "error");
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = "Enviar avaliação";
                }
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
