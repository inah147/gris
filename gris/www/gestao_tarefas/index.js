/* /gestao_tarefas — criacao de quadros. */
(() => {
    "use strict";

    function callApi(method, args = {}) {
        return new Promise((resolve, reject) => {
            frappe.call({
                method,
                args,
                callback: (response) => {
                    const data = response?.message;
                    if (!data || data.ok === false) {
                        reject(new Error(data?.error || "Erro ao criar quadro."));
                        return;
                    }
                    resolve(data);
                },
                error: (err) => reject(err instanceof Error ? err : new Error(String(err))),
            });
        });
    }

    function init() {
        const btnCriar = document.getElementById("btn-criar-quadro");
        const input = document.getElementById("input-titulo-quadro");
        const dialog = document.getElementById("dialog-novo-quadro");

        if (!btnCriar || !input || !dialog) return;

        btnCriar.addEventListener("click", async () => {
            const titulo = (input.value || "").trim();
            if (!titulo) {
                input.focus();
                return;
            }

            btnCriar.disabled = true;
            try {
                const data = await callApi("gris.api.gestao_de_tarefas.quadros.criar_quadro", { titulo });
                frappe.show_alert?.({ message: "Quadro criado", indicator: "green" });
                window.location.href = `/gestao_tarefas/tarefas?board=${encodeURIComponent(data.name)}`;
            } catch (err) {
                frappe.msgprint?.({
                    title: "Nao foi possivel criar o quadro",
                    message: err.message || String(err),
                    indicator: "red",
                });
            } finally {
                btnCriar.disabled = false;
            }
        });

        input.addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                event.preventDefault();
                btnCriar.click();
            }
        });

        document.querySelectorAll("[data-dialog-close]").forEach((btn) => {
            btn.addEventListener("click", () => {
                const targetId = btn.getAttribute("data-dialog-close");
                const target = targetId && document.getElementById(targetId);
                if (target && typeof target.close === "function") target.close();
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
