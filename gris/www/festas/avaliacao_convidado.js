(function () {
    "use strict";

    var SUBMIT_METHOD =
        "gris.festas.doctype.avaliacao_festa.avaliacao_festa.submeter_avaliacao_convidado";

    function getToken() {
        return (document.getElementById("avaliacaoToken") || {}).value || "";
    }

    function showFormAlert(message) {
        var el = document.getElementById("avaliacaoAlert");
        if (!el) return;
        el.className = "alert alert-destructive";
        el.setAttribute("role", "alert");
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

    function openDuplicateDialog() {
        var dlg = document.getElementById("dialogDuplicado");
        if (dlg && typeof dlg.showModal === "function") {
            dlg.showModal();
        }
    }

    function handleSubmit(event) {
        event.preventDefault();
        hideFormAlert();

        var token = getToken();
        if (!token) {
            showFormAlert("Link de avaliação inválido.");
            return;
        }

        var recomendacao = getSelectedRadio("recomendacao");
        var email = (document.getElementById("convidado_email") || {}).value || "";
        var maisGostou = (document.getElementById("mais_gostou") || {}).value || "";
        var podeMelhorar = (document.getElementById("pode_melhorar") || {}).value || "";

        if (recomendacao === null) {
            showFormAlert("Por favor, escolha o quanto você recomendaria a festa (0 a 10).");
            return;
        }
        if (!maisGostou.trim()) {
            showFormAlert("Por favor, conte o que você mais gostou na festa.");
            return;
        }
        if (!podeMelhorar.trim()) {
            showFormAlert("Por favor, conte o que você acha que pode melhorar.");
            return;
        }

        var btn = document.getElementById("btnSubmitAvaliacao");
        setSubmitLoading(btn, true);

        frappe.call({
            method: SUBMIT_METHOD,
            args: {
                token: token,
                email: email.trim(),
                recomendacao: recomendacao,
                mais_gostou: maisGostou.trim(),
                pode_melhorar: podeMelhorar.trim(),
            },
            callback: function (r) {
                var msg = r && r.message;
                if (msg && msg.ok) {
                    showState("stateSuccess");
                } else if (msg && msg.duplicate) {
                    openDuplicateDialog();
                    setSubmitLoading(btn, false);
                } else {
                    showFormAlert("Erro ao enviar avaliação. Tente novamente.");
                    setSubmitLoading(btn, false);
                }
            },
            error: function () {
                showFormAlert("Erro de comunicação com o servidor. Tente novamente.");
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
