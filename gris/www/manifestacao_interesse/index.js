frappe.ready(function() {
    
    // CPF Masking
    // Removed initial binding here as it is handled by applyMasks() and addJovem()
    
    // Phone Masking (Simple numbers only enforcement visually, though validation handles it)
    $('#celular_responsavel').on('input', function() {
        this.value = this.value.replace(/\D/g, '');
    });

    // Dynamic Jovem Forms
    function updateJovensForms() {
        const qtd = parseInt($('#qtd_jovens').val()) || 1;
        const container = $('#jovens-container');
        const currentCount = container.children().length;
        const template = document.getElementById('jovem-template');

        if (qtd > currentCount) {
            // Add more forms
            for (let i = currentCount; i < qtd; i++) {
                const clone = template.content.cloneNode(true);
                $(clone).find('.jovem-title').text(`Jovem ${i + 1}`);
                container.append(clone);
            }
        } else if (qtd < currentCount) {
            // Remove excess forms
            container.children().slice(qtd).remove();
        }
        
        // Re-apply masks to new inputs
        applyMasks();
    }

    function applyMasks() {
        $('#cpf_responsavel, .cpf_jovem').off('input').on('input', function() {
            let value = $(this).val().replace(/\D/g, '');
            if (value.length > 11) value = value.slice(0, 11);
            
            if (value.length > 9) {
                value = value.replace(/^(\d{3})(\d{3})(\d{3})(\d{1,2}).*/, '$1.$2.$3-$4');
            } else if (value.length > 6) {
                value = value.replace(/^(\d{3})(\d{3})(\d{1,3}).*/, '$1.$2.$3');
            } else if (value.length > 3) {
                value = value.replace(/^(\d{3})(\d{1,3}).*/, '$1.$2');
            }
            $(this).val(value);
        });
    }

    // Initialize first Jovem
    updateJovensForms();

    // Event Listeners for Quantity Change
    $('#qtd_jovens').on('change input', updateJovensForms);

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

    function validateName(name) {
        // Only letters and spaces
        const re = /^[a-zA-Z\u00C0-\u00FF\s]+$/;
        return re.test(name);
    }

    function validateDate(dateString) {
        if(!dateString) return false;
        const date = new Date(dateString);
        const today = new Date();
        today.setHours(0,0,0,0);
        return date instanceof Date && !isNaN(date) && date < today;
    }

    function validateTab(tabId) {
        let isValid = true;
        const tab = $(tabId);
        
        // Reset validations in this tab
        tab.find('.is-invalid').removeClass('is-invalid');

        // Validate fields inside this tab
        if (tabId === '#responsavel') {
            // Validate Name
            const nameField = $('#nome_responsavel');
            if (!validateName(nameField.val())) {
                nameField.addClass('is-invalid');
                isValid = false;
            }

            // Validate Email
            const emailField = $('#email_responsavel');
            if (!validateEmail(emailField.val())) {
                emailField.addClass('is-invalid');
                isValid = false;
            }

            // Validate Phone
            const phoneField = $('#celular_responsavel');
            if (!/^\d+$/.test(phoneField.val())) {
                phoneField.addClass('is-invalid');
                isValid = false;
            }

            // Validate CPF
            const cpfField = $('#cpf_responsavel');
            if (!validateCPF(cpfField.val())) {
                cpfField.addClass('is-invalid');
                isValid = false;
            }
        } else if (tabId === '#jovem') {
            // Validate All Jovens
            $('.jovem-entry').each(function() {
                const entry = $(this);
                
                // Validate Name Jovem
                const nameJovemField = entry.find('.nome_jovem');
                if (!validateName(nameJovemField.val())) {
                    nameJovemField.addClass('is-invalid');
                    isValid = false;
                }

                // Validate CPF Jovem
                const cpfJovemField = entry.find('.cpf_jovem');
                if (!validateCPF(cpfJovemField.val())) {
                    cpfJovemField.addClass('is-invalid');
                    isValid = false;
                }

                // Validate Date Jovem
                const dateJovemField = entry.find('.data_nascimento_jovem');
                if (!validateDate(dateJovemField.val())) {
                    dateJovemField.addClass('is-invalid');
                    isValid = false;
                }
            });
        } else if (tabId === '#confirmacao') {
            const checkDados = $('#check_dados_corretos');
            if (!checkDados.is(':checked')) {
                checkDados.addClass('is-invalid');
                isValid = false;
            }

            const checkLgpd = $('#check_lgpd');
            if (!checkLgpd.is(':checked')) {
                checkLgpd.addClass('is-invalid');
                isValid = false;
            }
        }
        return isValid;
    }

    // Navigation Buttons
    $('.btn-next').on('click', function() {
        if (validateTab('#responsavel')) {
            $('#jovem-tab').removeClass('disabled').tab('show');
        }
    });

    $('.btn-next-jovem').on('click', function() {
        if (validateTab('#jovem')) {
            // Check for duplicate CPFs
            const cpfResponsavelField = $('#cpf_responsavel');
            const cpfResponsavel = cpfResponsavelField.val();
            let hasDuplicates = false;
            
            // Reset previous duplicate errors (specifically for duplicates, though validateTab clears some)
            // We need to ensure we don't clear other validation errors if we were to run this differently,
            // but here validateTab('#jovem') just ran and passed, so .cpf_jovem fields are valid format-wise.
            // #cpf_responsavel might have old invalid class if we don't clear it, but validateTab('#responsavel') isn't called here.
            cpfResponsavelField.removeClass('is-invalid');
            
            const seenCpfs = {}; // Map CPF -> Array of fields

            // Add Responsavel
            if (cpfResponsavel) {
                seenCpfs[cpfResponsavel] = [cpfResponsavelField];
            }

            // Add Jovens
            $('.jovem-entry').each(function() {
                const field = $(this).find('.cpf_jovem');
                const val = field.val();
                if (val) {
                    if (!seenCpfs[val]) {
                        seenCpfs[val] = [];
                    }
                    seenCpfs[val].push(field);
                }
            });

            // Check counts
            for (const cpf in seenCpfs) {
                if (seenCpfs[cpf].length > 1) {
                    hasDuplicates = true;
                    seenCpfs[cpf].forEach(field => field.addClass('is-invalid'));
                }
            }

            if (hasDuplicates) {
                frappe.msgprint({
                    title: 'Erro de Validação',
                    indicator: 'red',
                    message: 'Existem CPFs duplicados (Responsável ou Jovens). Cada pessoa deve ter um CPF único.'
                });
                return;
            }

            // Enable confirmation tab
            $('#confirmacao-tab').removeClass('disabled');
            
            // Populate Summary
            $('#summary_nome_responsavel').text($('#nome_responsavel').val());
            $('#summary_email_responsavel').text($('#email_responsavel').val());
            $('#summary_celular_responsavel').text($('#celular_responsavel').val());
            $('#summary_cpf_responsavel').text($('#cpf_responsavel').val());
            
            const summaryJovensContainer = $('#summary-jovens-container');
            summaryJovensContainer.empty();

            $('.jovem-entry').each(function(index) {
                const entry = $(this);
                const nome = entry.find('.nome_jovem').val();
                const cpf = entry.find('.cpf_jovem').val();
                const dataNasc = entry.find('.data_nascimento_jovem').val();
                
                let dataFormatada = '';
                if (dataNasc) {
                    const dateObj = new Date(dataNasc);
                    const userTimezoneOffset = dateObj.getTimezoneOffset() * 60000;
                    const adjustedDate = new Date(dateObj.getTime() + userTimezoneOffset);
                    dataFormatada = adjustedDate.toLocaleDateString('pt-BR');
                }

                const html = `
                    <div class="mb-3 pb-3 border-bottom ${index === $('.jovem-entry').length - 1 ? 'border-0 pb-0 mb-0' : ''}">
                        <h6 class="text-secondary mb-2">Jovem ${index + 1}</h6>
                        <div class="row g-3">
                            <div class="col-12 mb-2">
                                <small class="text-muted d-block text-uppercase" style="font-size: 0.75rem; letter-spacing: 0.5px;">Nome</small>
                                <span class="fw-bold text-dark">${nome}</span>
                            </div>
                            <div class="col-sm-6 mb-2">
                                <small class="text-muted d-block text-uppercase" style="font-size: 0.75rem; letter-spacing: 0.5px;">CPF</small>
                                <span class="fw-bold text-dark">${cpf}</span>
                            </div>
                            <div class="col-sm-6 mb-2">
                                <small class="text-muted d-block text-uppercase" style="font-size: 0.75rem; letter-spacing: 0.5px;">Data de Nascimento</small>
                                <span class="fw-bold text-dark">${dataFormatada}</span>
                            </div>
                        </div>
                    </div>
                `;
                summaryJovensContainer.append(html);
            });

            $('#confirmacao-tab').tab('show');
        }
    });

    $('.btn-prev').on('click', function() {
        $('#responsavel-tab').tab('show');
    });

    $('.btn-prev-confirmacao').on('click', function() {
        $('#jovem-tab').tab('show');
    });

    $('#interest-form').on('submit', function(e) {
        e.preventDefault();
        
        // Validate all tabs before submit
        if (!validateTab('#responsavel')) {
            $('#responsavel-tab').tab('show');
            return;
        }
        if (!validateTab('#jovem')) {
            $('#jovem-tab').tab('show');
            return;
        }
        if (!validateTab('#confirmacao')) {
            // Already on this tab usually
            return;
        }

        var data = {};
        // Collect Responsavel Data
        data['nome_responsavel'] = $('#nome_responsavel').val();
        data['email_responsavel'] = $('#email_responsavel').val();
        data['celular_responsavel'] = $('#celular_responsavel').val();
        data['cpf_responsavel'] = $('#cpf_responsavel').val();

        // Collect Jovens Data
        var jovens = [];
        $('.jovem-entry').each(function() {
            var entry = $(this);
            jovens.push({
                'nome_jovem': entry.find('.nome_jovem').val(),
                'cpf_jovem': entry.find('.cpf_jovem').val(),
                'data_nascimento_jovem': entry.find('.data_nascimento_jovem').val()
            });
        });
        data['jovens'] = JSON.stringify(jovens);

        frappe.call({
            method: 'gris.gris.www.manifestacao_interesse.index.submit_interest',
            args: data,
            freeze: true,
            freeze_message: 'Enviando...',
            callback: function(r) {
                if (r.message && r.message.status === 'success') {
                    $('#interest-form').slideUp();
                    $('#form-message').html(`
                        <div class="alert alert-success">
                            <h4 class="alert-heading">Sucesso!</h4>
                            <p>${r.message.message}</p>
                        </div>
                    `).fadeIn();
                    
                    // Update Stepper
                    $('#step-1').removeClass('active').addClass('completed');
                    $('#step-1 .step-counter').html('<i class="fa fa-check"></i>');
                    $('#step-2').addClass('active');
                    
                } else {
                    frappe.msgprint({
                        title: 'Erro',
                        indicator: 'red',
                        message: r.message ? r.message.message : 'Ocorreu um erro desconhecido.'
                    });
                }
            },
            error: function(r) {
                frappe.msgprint({
                    title: 'Erro',
                    indicator: 'red',
                    message: 'Não foi possível conectar ao servidor. Tente novamente mais tarde.'
                });
            }
        });
    });
});
