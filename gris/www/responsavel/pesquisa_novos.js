frappe.ready(function() {
    const form = document.getElementById('survey-form');
    if (!form) return;

    form.addEventListener('submit', function(e) {
        e.preventDefault();
        
        const formData = new FormData(form);
        const data = {};
        
        // Handle standard inputs
        for (let [key, value] of formData.entries()) {
            data[key] = value;
        }

        // Validate required fields (optional, but good practice)
        if (!data.como_conheceu_movimento || !data.como_voce_conheceu_grupo || !data.nps_recepcao) {
            frappe.msgprint({
                title: 'Campos Obrigatórios',
                message: 'Por favor, preencha todos os campos de seleção e a nota NPS.',
                indicator: 'orange'
            });
            return;
        }

        frappe.call({
            method: "gris.www.responsavel.pesquisa_novos.submit_survey",
            args: {
                data: JSON.stringify(data)
            },
            freeze: true,
            freeze_message: "Enviando...",
            callback: function(r) {
                if (!r.exc) {
                    frappe.msgprint({
                        title: 'Sucesso',
                        message: r.message,
                        indicator: 'green'
                    });
                    setTimeout(() => {
                        window.location.reload();
                    }, 2000);
                }
            }
        });
    });
});
