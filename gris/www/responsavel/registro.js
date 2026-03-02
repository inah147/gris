frappe.ready(function() {

    // --- Validation Helpers ---

    function validateCPF(cpf) {
        cpf = cpf.replace(/[^\d]+/g, '');
        if (cpf == '') return false;
        // Elimina CPFs invalidos conhecidos
        if (cpf.length != 11 || 
            cpf == "00000000000" || 
            cpf == "11111111111" || 
            cpf == "22222222222" || 
            cpf == "33333333333" || 
            cpf == "44444444444" || 
            cpf == "55555555555" || 
            cpf == "66666666666" || 
            cpf == "77777777777" || 
            cpf == "88888888888" || 
            cpf == "99999999999")
                return false;
        // Valida 1o digito
        let add = 0;
        for (let i = 0; i < 9; i++) 
            add += parseInt(cpf.charAt(i)) * (10 - i);
        let rev = 11 - (add % 11);
        if (rev == 10 || rev == 11) 
            rev = 0;
        if (rev != parseInt(cpf.charAt(9))) 
            return false;
        // Valida 2o digito
        add = 0;
        for (let i = 0; i < 10; i++) 
            add += parseInt(cpf.charAt(i)) * (11 - i);
        rev = 11 - (add % 11);
        if (rev == 10 || rev == 11) 
            rev = 0;
        if (rev != parseInt(cpf.charAt(10))) 
            return false;
        return true;
    }

    function validateEmail(email) {
        const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return re.test(email);
    }

    function applyPhoneMask(input) {
        let value = input.val().replace(/\D/g, '');
        if (value.length > 11) value = value.slice(0, 11);
        
        if (value.length > 10) {
            // (XX) X XXXX-XXXX
            value = value.replace(/^(\d{2})(\d{1})(\d{4})(\d{4}).*/, '($1) $2 $3-$4');
        } else if (value.length > 6) {
            // (XX) XXXX-XXXX
            value = value.replace(/^(\d{2})(\d{4})(\d{0,4})/, '($1) $2-$3');
        } else if (value.length > 2) {
            value = value.replace(/^(\d{2})(\d{0,5})/, '($1) $2');
        }
        input.val(value);
    }

    function applyCPFMask(input) {
        let value = input.val().replace(/\D/g, '');
        if (value.length > 11) value = value.slice(0, 11);
        
        if (value.length > 9) {
            value = value.replace(/^(\d{3})(\d{3})(\d{3})(\d{1,2}).*/, '$1.$2.$3-$4');
        } else if (value.length > 6) {
            value = value.replace(/^(\d{3})(\d{3})(\d{1,3}).*/, '$1.$2.$3');
        } else if (value.length > 3) {
            value = value.replace(/^(\d{3})(\d{1,3}).*/, '$1.$2');
        }
        input.val(value);
    }

    // --- Event Listeners for Masks ---

    // Apply masks to main form fields
    $('#cpf').on('input', function() {
        applyCPFMask($(this));
    });

    $('#celular, #telefone_secundario, #telefone_cobranca').on('input', function() {
        applyPhoneMask($(this));
    });

    // Apply masks to responsible fields (using delegation)
    $(document).on('input', 'input[data-fieldname="cpf"]', function() {
        applyCPFMask($(this));
    });

    $(document).on('input', 'input[data-fieldname="celular"], input[data-fieldname="telefone_secundario"]', function() {
        applyPhoneMask($(this));
    });

    // --- Family Info Logic ---

    function toggleFamilyInfo() {
        const onlyOne = $('#somente_um_responsavel').is(':checked');

        // Somente um responsavel logic
        if (onlyOne) {
            // Hide all except first
            $('.responsavel-wrapper').each(function(index) {
                if (index > 0) {
                    $(this).hide();
                    $(this).find('.guardiao-legal-check').prop('checked', false);
                }
            });
        } else {
            // Show all
            $('.responsavel-wrapper').show();
        }

        toggleGuardiaoLegal();
    }

    function toggleGuardiaoLegal() {
        const isUnilateral = $('#guarda_unilateral').is(':checked');
        const checks = $('.guardiao-legal-check');
        const containers = $('.guardiao-legal-container');
        const sectionTitle = $('.responsavel-card .card-modern__subtitle').filter(function() {
            return $(this).text().trim() === 'Vínculo';
        });

        if (isUnilateral) {
            containers.show();
            sectionTitle.show();
            checks.prop('disabled', false);
            if (checks.filter(':checked').length !== 1) {
                checks.prop('checked', false);
                checks.first().prop('checked', true);
            }
        } else {
            checks.prop('checked', true).prop('disabled', true);
            containers.hide();
            sectionTitle.hide();
        }
    }

    $('#guarda_unilateral').on('change', toggleGuardiaoLegal);
    $('#somente_um_responsavel').on('change', toggleFamilyInfo);

    // Enforce single selection for Legal Guardian
    $(document).on('change', '.guardiao-legal-check', function() {
        if ($('#guarda_unilateral').is(':checked') && $(this).is(':checked')) {
            $('.guardiao-legal-check').not(this).prop('checked', false);
        }
    });

    // --- Same Address Logic ---

    function syncAddressToCard(card) {
        const fields = ['cep', 'endereco', 'numero', 'complemento', 'bairro', 'cidade', 'estado'];
        fields.forEach(field => {
            const mainVal = $(`#${field}`).val();
            const $target = card.find(`[data-fieldname="${field}"]`);
            $target.val(mainVal);
            if (mainVal) {
                $target.removeClass('is-invalid');
            }
        });
    }

    $(document).on('change', '.same-address-check', function() {
        const checkbox = $(this);
        const card = checkbox.closest('.responsavel-card');
        const fields = ['cep', 'endereco', 'numero', 'complemento', 'bairro', 'cidade', 'estado'];
        
        if (checkbox.is(':checked')) {
            syncAddressToCard(card);
            fields.forEach(field => {
                card.find(`[data-fieldname="${field}"]`).prop('readonly', true).addClass('disabled');
            });
        } else {
            fields.forEach(field => {
                card.find(`[data-fieldname="${field}"]`).prop('readonly', false).removeClass('disabled');
            });
        }
    });

    // Sync when main address changes
    const addressFields = ['cep', 'endereco', 'numero', 'complemento', 'bairro', 'cidade', 'estado'];
    addressFields.forEach(field => {
        $(`#${field}`).on('input change', function() {
            $('.same-address-check:checked').each(function() {
                const card = $(this).closest('.responsavel-card');
                const mainVal = $(`#${field}`).val();
                const $target = card.find(`[data-fieldname="${field}"]`);
                $target.val(mainVal);
                if (mainVal) {
                    $target.removeClass('is-invalid');
                }
            });
        });
    });

    // Initial state
    toggleFamilyInfo();

    // Update card title when name changes
    $(document).on('input', 'input[data-fieldname="nome_completo"]', function() {
        const val = $(this).val();
        $(this).closest('.responsavel-card').find('.responsavel-card__title').text(val || 'Novo Responsável');
    });

    // Remove invalid class on input
    $(document).on('input change', '.is-invalid', function() {
        $(this).removeClass('is-invalid');
    });

    // --- Form Submission ---

    $('#registro-form').on('submit', function(e) {
        e.preventDefault();
        
        // Clear previous errors
        $('.is-invalid').removeClass('is-invalid');
        
        let isValid = true;
        let firstInvalidField = null;

        // --- Mandatory Fields Validation ---

        // Novo Associado Mandatory Fields
        const novoAssociadoMandatory = [
            'nome_completo', 'data_de_nascimento', 'etnia', 'sexo', 
            'pais_nascimento', 'uf_de_nascimento', 'cidade_de_nascimento',
            'rg', 'orgao_expedidor', 'cpf', 'estado_civil', 'religiao', 'escolaridade',
            'cep', 'endereco', 'numero', 'bairro', 'estado', 'cidade', 'email', 'celular',
            'email_cobranca', 'telefone_cobranca'
        ];

        novoAssociadoMandatory.forEach(fieldId => {
            const field = $(`#${fieldId}`);
            if (!field.val()) {
                field.addClass('is-invalid');
                isValid = false;
                if (!firstInvalidField) firstInvalidField = field;
            }
        });

        // Responsavel Mandatory Fields
        const responsavelMandatory = [
            'nome_completo', 'cpf', 'rg', 'orgao_expedidor', 'data_de_nascimento',
            'sexo', 'estado_civil', 'escolaridade', 'profissao', 'local_de_trabalho',
            'cep', 'endereco', 'numero', 'bairro', 'cidade', 'estado', 'email', 'celular'
        ];

        $('.responsavel-card').each(function() {
            const card = $(this);
            
            // Skip validation if hidden (e.g. "Somente um responsável" checked)
            if (card.is(':hidden')) return;

            responsavelMandatory.forEach(fieldName => {
                const field = card.find(`[data-fieldname="${fieldName}"]`);
                if (!field.val()) {
                    field.addClass('is-invalid');
                    isValid = false;
                    if (!firstInvalidField) firstInvalidField = field;
                }
            });
        });

        if (!isValid) {
            frappe.msgprint({
                title: 'Campos Obrigatórios',
                indicator: 'red',
                message: 'Por favor, preencha todos os campos obrigatórios.'
            });
            if (firstInvalidField) {
                $('html, body').animate({
                    scrollTop: firstInvalidField.offset().top - 100
                }, 500);
                firstInvalidField.focus();
            }
            return;
        }

        // Validate CPF (Main)
        const cpfField = $('#cpf');
        if (cpfField.val() && !validateCPF(cpfField.val())) {
            cpfField.addClass('is-invalid');
            frappe.msgprint({
                title: 'Erro de Validação',
                indicator: 'red',
                message: 'CPF do Associado inválido.'
            });
            isValid = false;
        }

        // Validate Email (Main)
        const emailField = $('#email');
        if (emailField.val() && !validateEmail(emailField.val())) {
            emailField.addClass('is-invalid');
            frappe.msgprint({
                title: 'Erro de Validação',
                indicator: 'red',
                message: 'Email do Associado inválido.'
            });
            isValid = false;
        }

        // Validate Billing Email
        const emailCobrancaField = $('#email_cobranca');
        if (emailCobrancaField.val() && !validateEmail(emailCobrancaField.val())) {
            emailCobrancaField.addClass('is-invalid');
            frappe.msgprint({
                title: 'Erro de Validação',
                indicator: 'red',
                message: 'Email de cobrança inválido.'
            });
            isValid = false;
        }

        // Validate Phone (Main)
        const celularField = $('#celular');
        const celularVal = celularField.val().replace(/\D/g, '');
        if (celularVal && celularVal.length < 10) {
            celularField.addClass('is-invalid');
            frappe.msgprint({
                title: 'Erro de Validação',
                indicator: 'red',
                message: 'Celular do Associado inválido.'
            });
            isValid = false;
        }

        // Validate Billing Phone
        const telefoneCobrancaField = $('#telefone_cobranca');
        const telefoneCobrancaVal = telefoneCobrancaField.val().replace(/\D/g, '');
        if (telefoneCobrancaVal && telefoneCobrancaVal.length < 10) {
            telefoneCobrancaField.addClass('is-invalid');
            frappe.msgprint({
                title: 'Erro de Validação',
                indicator: 'red',
                message: 'Telefone de cobrança inválido.'
            });
            isValid = false;
        }

        // Validate Responsibles
        $('.responsavel-card').each(function() {
            const card = $(this);
            const name = card.find('.responsavel-card__title').text();

            // CPF
            const respCpfField = card.find('input[data-fieldname="cpf"]');
            if (respCpfField.val() && !validateCPF(respCpfField.val())) {
                respCpfField.addClass('is-invalid');
                frappe.msgprint({
                    title: 'Erro de Validação',
                    indicator: 'red',
                    message: `CPF do responsável ${name} inválido.`
                });
                isValid = false;
            }

            // Email
            const respEmailField = card.find('input[data-fieldname="email"]');
            if (respEmailField.val() && !validateEmail(respEmailField.val())) {
                respEmailField.addClass('is-invalid');
                frappe.msgprint({
                    title: 'Erro de Validação',
                    indicator: 'red',
                    message: `Email do responsável ${name} inválido.`
                });
                isValid = false;
            }
        });

        if (!isValid) return;

        let $btn = $(this).find('button[type="submit"]');
        let btnText = $btn.text();
        $btn.prop('disabled', true).text('Salvando...');

        // Collect Main Data
        let form_data = {};
        $(this).serializeArray().forEach(function(item) {
            // Only collect fields that are NOT inside a responsavel-card (which don't have name attr anyway now)
            // But wait, serializeArray picks up all inputs with name attribute.
            // I removed name attribute from responsible inputs and used data-fieldname.
            // So serializeArray should only pick up main form fields.
            if (item.name) {
                form_data[item.name] = item.value;
            }
        });

        // Handle checkboxes explicitly
        form_data['estrangeiro'] = $('#estrangeiro').is(':checked') ? 1 : 0;
        form_data['guarda_unilateral'] = $('#guarda_unilateral').is(':checked') ? 1 : 0;

        let novo_associado_name = form_data['name'];
        delete form_data['name'];

        // Collect Responsibles Data
        let responsaveis_data = [];
        $('.responsavel-card').each(function() {
            const card = $(this);
            const respId = card.data('responsavel-id'); // Can be empty for new ones
            let respData = {
                name: respId
            };
            
            card.find('input[data-fieldname], select[data-fieldname]').each(function() {
                const field = $(this);
                const fieldName = field.data('fieldname');
                if (field.attr('type') === 'checkbox') {
                    respData[fieldName] = field.is(':checked') ? 1 : 0;
                } else {
                    respData[fieldName] = field.val();
                }
            });
            
            responsaveis_data.push(respData);
        });

        const isUnilateral = form_data['guarda_unilateral'] === 1;
        const visibleChecks = $('.responsavel-wrapper:visible .guardiao-legal-check');
        const checksToValidate = visibleChecks.length ? visibleChecks : $('.guardiao-legal-check');

        if (isUnilateral) {
            const checkedCount = checksToValidate.filter(':checked').length;
            if (checkedCount !== 1) {
                frappe.msgprint({
                    title: 'Validação de Guarda',
                    indicator: 'red',
                    message: 'Com guarda unilateral, exatamente um responsável deve ser marcado como guardião legal.'
                });
                $btn.prop('disabled', false).text(btnText);
                return;
            }
        } else {
            $('.guardiao-legal-check').prop('checked', true);
            responsaveis_data.forEach(resp => {
                if (resp.nome_completo || resp.cpf || resp.name) {
                    resp['é_guardiao_legal'] = 1;
                }
            });
        }

        // Open Type Selection Modal first instead of Confirmation directly
        openTipoRegistroModal(novo_associado_name, form_data, responsaveis_data, $btn, btnText);
    });

    // --- Modal Logic ---
    const $modal = $('#confirmationModal');
    const $backdrop = $('#confirmationModalBackdrop');

    function openModal() {
        $modal.css('display', 'flex');
        $backdrop.css('display', 'block');
        // Force reflow
        $modal[0].offsetHeight;
        
        $modal.addClass('show');
        $backdrop.addClass('show');
        $('body').addClass('modal-open');
    }

    function closeModal() {
        $modal.removeClass('show');
        $backdrop.removeClass('show');
        $('body').removeClass('modal-open');
        
        setTimeout(() => {
            $modal.css('display', 'none');
            $backdrop.css('display', 'none');
        }, 300);
    }

    // Close handlers
    $modal.find('[data-bs-dismiss="modal"]').on('click', closeModal);
    // Close on backdrop click (if clicking outside modal content)
    $modal.on('click', function(e) {
        if (e.target === this) {
            closeModal();
        }
    });

    function showConfirmationModal(novo_associado_name, form_data, responsaveis_data, $btn, btnText) {
        const summaryContainer = document.getElementById('confirmation-summary');
        const confirmCheck = document.getElementById('confirm-data-check');
        const confirmImageCheck = document.getElementById('confirm-image-check');
        const confirmBtn = document.getElementById('btn-confirm-save');

        // Reset state
        confirmCheck.checked = false;
        confirmImageCheck.checked = false;
        confirmBtn.disabled = true;
        $btn.prop('disabled', false).text(btnText); // Reset main button

        function formatLabel(key) {
            const labelMap = {
                'tipo_de_registro': 'Tipo de Registro',
                'nome_completo': 'Nome Completo',
                'data_de_nascimento': 'Data de Nascimento',
                'pais_nascimento': 'País de Nascimento',
                'uf_de_nascimento': 'UF de Nascimento',
                'cidade_de_nascimento': 'Cidade de Nascimento',
                'orgao_expedidor': 'Órgão Expedidor',
                'estado_civil': 'Estado Civil',
                'telefone_secundario': 'Telefone Secundário',
                'guarda_unilateral': 'Guarda Unilateral',
                'somente_um_responsavel': 'Somente um Responsável',
                'local_de_trabalho': 'Local de Trabalho',
                'é_guardiao_legal': 'É Guardião Legal',
                'cpf': 'CPF',
                'rg': 'RG',
                'cep': 'CEP',
                'uf': 'UF',
                'email': 'Email',
                'celular': 'Celular',
                'email_cobranca': 'Email de Cobrança',
                'telefone_cobranca': 'Telefone de Cobrança',
                'endereco': 'Endereço',
                'numero': 'Número',
                'complemento': 'Complemento',
                'bairro': 'Bairro',
                'cidade': 'Cidade',
                'estado': 'Estado',
                'etnia': 'Etnia',
                'sexo': 'Sexo',
                'religiao': 'Religião',
                'escolaridade': 'Escolaridade',
                'profissao': 'Profissão',
                'estrangeiro': 'Estrangeiro'
            };
            
            if (labelMap[key]) return labelMap[key];
            return key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
        }

        function formatValue(key, value) {
            if (value === 1 || value === '1' || value === true) return 'Sim';
            if (value === 0 || value === '0' || value === false) return 'Não';
            if (!value) return '-';
            return value;
        }

        // Build Summary HTML
        let html = `<h6 class="fw-bold border-bottom pb-2 mb-3">Novo Associado</h6>
                    <div class="row g-2 mb-4">`;
        
        const mainFieldsOrder = [
            'tipo_de_registro', 'nome_completo', 'cpf', 'rg', 'data_de_nascimento', 'email', 'celular',
            'email_cobranca', 'telefone_cobranca',
            'cep', 'endereco', 'numero', 'complemento', 'bairro', 'cidade', 'estado'
        ];
        
        const renderField = (key, value) => {
            if (key === 'csrf_token' || key === 'cmd') return '';
            return `<div class="col-md-6">
                        <strong>${formatLabel(key)}:</strong> ${formatValue(key, value)}
                    </div>`;
        };

        // Render ordered fields first
        mainFieldsOrder.forEach(key => {
            if (form_data.hasOwnProperty(key)) {
                html += renderField(key, form_data[key]);
            }
        });

        // Render remaining fields
        Object.keys(form_data).forEach(key => {
            if (!mainFieldsOrder.includes(key)) {
                html += renderField(key, form_data[key]);
            }
        });
        
        html += `</div>`;

        responsaveis_data.forEach((resp, index) => {
            // Skip if it's a placeholder/empty responsible (check name or cpf)
            if (!resp.nome_completo && !resp.cpf) return;

            html += `
                <h6 class="fw-bold border-bottom pb-2 mb-3 mt-4">Responsável ${index + 1}</h6>
                <div class="row g-2">
            `;
            
            // Render ordered fields for responsible
            mainFieldsOrder.forEach(key => {
                if (resp.hasOwnProperty(key)) {
                    html += renderField(key, resp[key]);
                }
            });

            // Render remaining fields
            Object.keys(resp).forEach(key => {
                if (!mainFieldsOrder.includes(key) && key !== 'name') {
                    html += renderField(key, resp[key]);
                }
            });

            html += `</div>`;
        });

        summaryContainer.innerHTML = html;

        // Event Listeners
        const updateConfirmButton = function() {
            confirmBtn.disabled = !(confirmCheck.checked && confirmImageCheck.checked);
        };

        confirmCheck.onchange = updateConfirmButton;
        confirmImageCheck.onchange = updateConfirmButton;

        confirmBtn.onclick = function() {
            closeModal();
            
            // Trigger Save
            $btn.prop('disabled', true).text('Salvando...');
            
            frappe.call({
                method: 'gris.www.responsavel.registro.update_novo_associado',
                args: {
                    novo_associado_name: novo_associado_name,
                    data: JSON.stringify(form_data),
                    responsaveis_data: JSON.stringify(responsaveis_data)
                },
                freeze: true,
                freeze_message: 'Salvando...',
                callback: function(r) {
                    $btn.prop('disabled', false).text(btnText);
                    if (!r.exc) {
                        frappe.show_alert({
                            message: 'Dados atualizados com sucesso!',
                            indicator: 'green'
                        });
                        // Reload to show new responsible properly (with ID)
                        setTimeout(() => window.location.reload(), 1500);
                    }
                },
                error: function() {
                    $btn.prop('disabled', false).text(btnText);
                }
            });
        };

        openModal();
    }

    // --- Tipo Registro Modal Logic ---
    const $modalTipoWrapper = $('#modalTipoRegistro');
    // Re-use backdrop for simplicity or handle separately. 
    // Since existing modal logic handles backdrop manually, we should follow or adapt.
    // The existing openModal logic is a bit manual ($backdrop.css...), let's check it.

    function openTipoRegistroModal(novo_associado_name, form_data, responsaveis_data, $btn, btnText) {
        const $modal = $('#modalTipoRegistro');
        const $backdrop = $('#confirmationModalBackdrop'); // Reusing the backdrop
        
        // Reset state
        $('.registro-option-card').removeClass('selected');
        $('#selected-tipo-registro').val('');
        $('#btn-confirm-tipo-registro').prop('disabled', true);
        
        $modal.css('display', 'flex');
        $backdrop.css('display', 'block');
        // Force reflow
        $modal[0].offsetHeight;
        
        $modal.addClass('show');
        $backdrop.addClass('show');
        $('body').addClass('modal-open');

        // Setup Confirm Handler (Continuar)
        $('#btn-confirm-tipo-registro').off('click').on('click', function() {
            const selectedType = $('#selected-tipo-registro').val();
            
            // Add type to form_data
            form_data['tipo_de_registro'] = selectedType;

            // Close this modal
            $modal.removeClass('show');
            setTimeout(() => {
                $modal.css('display', 'none');
                // Don't hide backdrop yet because we will open next modal immediately
                
                // Open Confirmation Modal
                showConfirmationModal(novo_associado_name, form_data, responsaveis_data, $btn, btnText);
            }, 300);
        });

        // Close handlers specific to this modal if needed
         $modal.find('[data-bs-dismiss="modal"]').off('click').on('click', function() {
            closeTipoModal();
            // Reset main button
            $btn.prop('disabled', false).text(btnText);
         });
    }

    function closeTipoModal() {
        const $modal = $('#modalTipoRegistro');
        const $backdrop = $('#confirmationModalBackdrop');
        $modal.removeClass('show');
        $backdrop.removeClass('show');
        $('body').removeClass('modal-open');
        setTimeout(() => {
            $modal.css('display', 'none');
            $backdrop.css('display', 'none');
        }, 300);
    }

    // Option Selection Logic
    $('.registro-option-card').on('click', function() {
        $('.registro-option-card').removeClass('selected');
        $(this).addClass('selected');
        
        const value = $(this).data('value');
        $('#selected-tipo-registro').val(value);
        $('#btn-confirm-tipo-registro').prop('disabled', false);
    });

});
