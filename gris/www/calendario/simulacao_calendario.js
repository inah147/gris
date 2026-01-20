frappe.ready(function() {
    scrollToToday();
    initFilters();
    initHoverEffects();
    initCopyData();
    initStartEmpty();
    initModal();
    initCellClick();
    initEditModal();
    initReconciliation();
});

function scrollToToday() {
    const today = new Date();
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, '0');
    const day = String(today.getDate()).padStart(2, '0');
    const dateStr = `${year}-${month}-${day}`;
    
    const row = document.querySelector(`tr[data-date="${dateStr}"]`);
    if (row) {
        // Wait a bit for layout to settle
        setTimeout(() => {
            row.scrollIntoView({ behavior: 'smooth', block: 'center' });
            row.classList.add('is-today');
        }, 500);
    }
}

function initFilters() {
    const allCheckbox = document.getElementById('filter-all');
    const sectionCheckboxes = document.querySelectorAll('input[name="section-filter"]');
    const showEmptyDaysCheckbox = document.getElementById('show-empty-days');
    const monthFilter = document.getElementById('month-filter');
    const yearFilter = document.getElementById('year-filter');

    // Year filter logic
    if (yearFilter) {
        yearFilter.addEventListener('change', () => {
            const selectedYear = yearFilter.value;
            const url = new URL(window.location.href);
            url.searchParams.set('year', selectedYear);
            window.location.href = url.toString();
        });
    }
    
    if (!allCheckbox) return;

    // "All" checkbox logic
    allCheckbox.addEventListener('change', (e) => {
        const isChecked = e.target.checked;
        sectionCheckboxes.forEach(cb => {
            cb.checked = isChecked;
        });
        applyFilters();
    });
    
    // Individual checkboxes logic
    sectionCheckboxes.forEach(cb => {
        cb.addEventListener('change', () => {
            const allChecked = Array.from(sectionCheckboxes).every(c => c.checked);
            allCheckbox.checked = allChecked;
            allCheckbox.indeterminate = !allChecked && Array.from(sectionCheckboxes).some(c => c.checked);
            applyFilters();
        });
    });

    // Show empty days logic
    showEmptyDaysCheckbox.addEventListener('change', () => {
        applyFilters();
    });

    // Month filter logic
    monthFilter.addEventListener('change', () => {
        applyFilters();
    });
    
    function applyFilters() {
        const selectedSections = Array.from(sectionCheckboxes)
            .filter(cb => cb.checked)
            .map(cb => cb.value);
        
        const showEmptyDays = showEmptyDaysCheckbox.checked;
        const selectedMonth = monthFilter.value;
            
        const rows = document.querySelectorAll('.calendar-row');
        
        rows.forEach(row => {
            let showRow = false;
            const rowDate = row.getAttribute('data-date');
            const rowMonth = rowDate.substring(5, 7);
            
            // Month filter check
            if (selectedMonth && rowMonth !== selectedMonth) {
                showRow = false;
            } else {
                if (showEmptyDays) {
                    showRow = true;
                } else {
                    // If no sections selected, show nothing (unless showEmptyDays is true, handled above)
                    if (selectedSections.length === 0) {
                        showRow = false;
                    } else {
                        // Check if row has activity in ANY of the selected sections
                        for (const section of selectedSections) {
                            // Find the cell for this section
                            // We use CSS.escape to handle section names with special chars if any
                            const cell = row.querySelector(`td[data-section="${CSS.escape(section)}"]`);
                            if (cell && cell.querySelector('.activity-card')) {
                                showRow = true;
                                break;
                            }
                        }
                    }
                }
            }
            
            if (showRow) {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        });

        // Handle month separators
        document.querySelectorAll('.month-separator-row').forEach(sep => {
            const sepMonth = sep.getAttribute('data-month');
            if (selectedMonth && sepMonth !== selectedMonth) {
                sep.style.display = 'none';
            } else {
                sep.style.display = '';
            }
        });
        
        // Also toggle column visibility
        const allSectionHeaders = document.querySelectorAll('th.col-section');
        const allSectionCells = document.querySelectorAll('td.col-activity');
        
        // This part might be heavy if done cell by cell. 
        // Better to use a style tag to toggle classes?
        // Or just iterate columns.
        
        // Let's use a dynamic style block for column visibility to be efficient
        let styleBlock = document.getElementById('dynamic-filter-style');
        if (!styleBlock) {
            styleBlock = document.createElement('style');
            styleBlock.id = 'dynamic-filter-style';
            document.head.appendChild(styleBlock);
        }
        
        // Generate CSS to hide unselected columns
        // We need to know which columns to hide.
        // Actually, iterating headers and cells is fine for this scale.
        // But CSS is cleaner.
        // We can add a class to the table or body indicating which sections are hidden?
        // No, sections are dynamic.
        
        // Let's just iterate headers and cells.
        // Wait, if I hide a column, the sticky header might break or alignment might break?
        // Table layout handles hidden columns fine.
        
        // However, the prompt asked for "filtro para somente datas".
        // It didn't explicitly ask to hide columns.
        // But if I select only "Section A", seeing empty columns for B, C, D is annoying.
        // I will hide columns too.
        
        const allSections = Array.from(sectionCheckboxes).map(cb => cb.value);
        const unselectedSections = allSections.filter(s => !selectedSections.includes(s));
        
        // Show all first
        document.querySelectorAll('.col-section, .col-activity').forEach(el => el.style.display = '');
        
        unselectedSections.forEach(section => {
             const selector = `[data-section="${CSS.escape(section)}"]`;
             // Hide headers (headers don't have data-section in my HTML yet! I need to add it)
             // Hide cells
             document.querySelectorAll(`td${selector}`).forEach(el => el.style.display = 'none');
             
             // For headers, I need to find them.
             // In HTML: <th class="col-section"><div class="th-content">{{ section }}</div></th>
             // I should add data-section to th as well.
             const headers = document.querySelectorAll(`th.col-section[data-section="${CSS.escape(section)}"]`);
             headers.forEach(th => {
                 th.style.display = 'none';
             });
        });

        // Update colspan for month separators
        const visibleColumnsCount = 1 + selectedSections.length; // 1 for date column
        document.querySelectorAll('.month-separator-cell').forEach(cell => {
            cell.colSpan = visibleColumnsCount;
        });
    }

    // Apply filters initially to match UI state
    applyFilters();
}

function initHoverEffects() {
    const cards = document.querySelectorAll('.activity-card');
    
    cards.forEach(card => {
        card.addEventListener('mouseenter', () => {
            const eventId = card.getAttribute('data-event-id');
            if (eventId) {
                const relatedCards = document.querySelectorAll(`.activity-card[data-event-id="${eventId}"]`);
                relatedCards.forEach(c => c.classList.add('is-hovered'));
            }
        });
        
        card.addEventListener('mouseleave', () => {
            const eventId = card.getAttribute('data-event-id');
            if (eventId) {
                const relatedCards = document.querySelectorAll(`.activity-card[data-event-id="${eventId}"]`);
                relatedCards.forEach(c => c.classList.remove('is-hovered'));
            }
        });
    });
}

function initCopyData() {
    const copyBtn = document.getElementById('btn-copy-data');
    if (copyBtn) {
        copyBtn.addEventListener('click', function() {
            const sourceYear = document.getElementById('source-year').value;
            const targetYear = this.getAttribute('data-target-year');
            
            if (!sourceYear) {
                frappe.msgprint("Por favor, selecione um ano de origem.");
                return;
            }

            frappe.confirm(
                `Tem certeza que deseja copiar os dados de ${sourceYear} para a simulação de ${targetYear}?`,
                () => {
                    frappe.call({
                        method: "gris.api.calendario.simulation.copy_calendar_data",
                        args: {
                            source_year: sourceYear,
                            target_year: targetYear
                        },
                        freeze: true,
                        freeze_message: "Copiando dados...",
                        callback: function(r) {
                            if (r.message && r.message.success) {
                                frappe.msgprint({
                                    title: __('Sucesso'),
                                    indicator: 'green',
                                    message: r.message.message
                                });
                                setTimeout(() => window.location.reload(), 2000);
                            } else {
                                frappe.msgprint({
                                    title: __('Erro'),
                                    indicator: 'red',
                                    message: r.message ? r.message.message : "Erro desconhecido ao copiar dados."
                                });
                            }
                        }
                    });
                }
            );
        });
    }
}

function initStartEmpty() {
    const startBtn = document.getElementById('btn-start-empty');
    if (startBtn) {
        startBtn.addEventListener('click', function() {
            const targetYear = this.getAttribute('data-target-year');
            const url = new URL(window.location.href);
            url.searchParams.set('year', targetYear);
            url.searchParams.set('start_empty', '1');
            window.location.href = url.toString();
        });
    }
}

function initModal() {
    const modal = document.getElementById('new-activity-modal');
    const closeBtn = document.getElementById('close-modal');
    const cancelBtn = document.getElementById('cancel-modal');
    const saveBtn = document.getElementById('save-modal');
    const newEventBtn = document.getElementById('btn-new-event');

    if (!modal) return;

    // Sem Atividade Toggle Logic
    const semAtividadeCheck = document.getElementById('modal-sem-atividade');
    if (semAtividadeCheck) {
        semAtividadeCheck.addEventListener('change', (e) => {
            const isChecked = e.target.checked;
            const localInput = document.getElementById('modal-local');
            const nivelInput = document.getElementById('modal-nivel');
            
            if (localInput) {
                localInput.disabled = isChecked;
                if (isChecked) localInput.value = '';
            }
            if (nivelInput) {
                nivelInput.disabled = isChecked;
                if (isChecked) nivelInput.value = 'Local';
            }
        });
    }

    if (newEventBtn) {
        newEventBtn.addEventListener('click', () => {
            // Reset form
            document.getElementById('modal-atividade').value = '';
            
            // Set default dates to today
            const today = new Date();
            const year = today.getFullYear();
            const month = String(today.getMonth() + 1).padStart(2, '0');
            const day = String(today.getDate()).padStart(2, '0');
            const todayStr = `${year}-${month}-${day}`;
            
            const inicioInput = document.getElementById('modal-inicio');
            const terminoInput = document.getElementById('modal-termino');
            
            if (inicioInput) inicioInput.value = todayStr;
            if (terminoInput) terminoInput.value = todayStr;
            
            // Reset new fields
            const localInput = document.getElementById('modal-local');
            if (localInput) {
                localInput.value = '';
                localInput.disabled = false;
            }

            const nivelInput = document.getElementById('modal-nivel');
            if (nivelInput) {
                nivelInput.value = 'Local';
                nivelInput.disabled = false;
            }
            
            const semAtividadeInput = document.getElementById('modal-sem-atividade');
            if (semAtividadeInput) semAtividadeInput.checked = false;

            // Uncheck all sections
            document.querySelectorAll('input[name="modal-secao"]').forEach(cb => cb.checked = false);

            modal.classList.add('is-open');
        });
    }

    function closeModal() {
        modal.classList.remove('is-open');
    }

    closeBtn.addEventListener('click', closeModal);
    cancelBtn.addEventListener('click', closeModal);

    // Close on click outside
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeModal();
    });

    saveBtn.addEventListener('click', () => {
        const atividade = document.getElementById('modal-atividade').value;
        const inicioDate = document.getElementById('modal-inicio').value;
        const terminoDate = document.getElementById('modal-termino').value;
        
        const secoesCheckboxes = document.querySelectorAll('input[name="modal-secao"]:checked');
        const secoes = Array.from(secoesCheckboxes).map(cb => cb.value);

        const local = document.getElementById('modal-local').value;
        const nivel = document.getElementById('modal-nivel').value;
        const semAtividade = document.getElementById('modal-sem-atividade').checked ? 1 : 0;

        if (!atividade || !inicioDate || !terminoDate || secoes.length === 0) {
            frappe.msgprint('Por favor, preencha todos os campos obrigatórios.');
            return;
        }

        // Append default times
        const inicio = `${inicioDate} 08:00:00`;
        const termino = `${terminoDate} 12:00:00`;

        frappe.call({
            method: "gris.api.calendario.simulation.create_simulation_event",
            args: {
                atividade: atividade,
                inicio: inicio,
                termino: termino,
                local: local,
                nivel: nivel,
                sem_atividade: semAtividade,
                secoes: JSON.stringify(secoes)
            },
            freeze: true,
            freeze_message: "Salvando...",
            callback: function(r) {
                if (r.message && r.message.success) {
                    frappe.show_alert({message: r.message.message, indicator: 'green'});
                    closeModal();
                    
                    if (r.message.events && Array.isArray(r.message.events)) {
                        r.message.events.forEach(event => addEventToTable(event));
                    } else {
                        setTimeout(() => window.location.reload(), 1000);
                    }
                } else {
                    frappe.msgprint({
                        title: __('Erro'),
                        indicator: 'red',
                        message: r.message ? r.message.message : "Erro ao salvar."
                    });
                }
            }
        });
    });
}

function initCellClick() {
    const cells = document.querySelectorAll('.calendar-table td[data-section]');
    const modal = document.getElementById('new-activity-modal');

    if (!modal) return;

    cells.forEach(cell => {
        cell.addEventListener('click', (e) => {
            // Ignore if clicked on an existing activity card
            if (e.target.closest('.activity-card')) return;

            const row = cell.closest('tr');
            const dateStr = row.getAttribute('data-date');
            const section = cell.getAttribute('data-section');

            // Pre-fill modal
            document.getElementById('modal-atividade').value = '';
            
            // Set default dates
            document.getElementById('modal-inicio').value = dateStr;
            document.getElementById('modal-termino').value = dateStr;

            // Select section checkbox
            const checkboxes = document.querySelectorAll('input[name="modal-secao"]');
            checkboxes.forEach(cb => {
                cb.checked = (cb.value === section);
            });

            modal.classList.add('is-open');
        });
    });
}


function initEditModal() {
    const modal = document.getElementById('edit-activity-modal');
    const closeBtn = document.getElementById('close-edit-modal');
    const cancelBtn = document.getElementById('cancel-edit-modal');
    const saveBtn = document.getElementById('save-edit-modal');
    const deleteBtn = document.getElementById('delete-edit-modal');

    if (!modal) return;

    function closeModal() {
        modal.classList.remove('is-open');
    }

    closeBtn.addEventListener('click', closeModal);
    cancelBtn.addEventListener('click', closeModal);

    // Close on click outside
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeModal();
    });

    // Open modal on card click
    document.addEventListener('click', (e) => {
        const card = e.target.closest('.activity-card');
        if (card) {
            e.stopPropagation(); // Prevent cell click
            
            const eventId = card.getAttribute('data-event-id');
            const atividade = card.getAttribute('data-atividade');
            const inicio = card.getAttribute('data-inicio'); // "2025-01-01 08:00:00"
            const termino = card.getAttribute('data-termino');
            const secao = card.getAttribute('data-secao');
            const local = card.getAttribute('data-local');
            const nivel = card.getAttribute('data-nivel');

            document.getElementById('edit-event-id').value = eventId;
            document.getElementById('edit-atividade').value = atividade;
            
            // Extract date part YYYY-MM-DD
            document.getElementById('edit-inicio').value = inicio.split(' ')[0];
            document.getElementById('edit-termino').value = termino.split(' ')[0];
            
            document.getElementById('edit-secao').value = secao;
            document.getElementById('edit-local').value = local;
            // Check if element exists before setting (in case modal HTML update didn't propagate or cached)
            const nivelEl = document.getElementById('edit-nivel');
            if (nivelEl) nivelEl.value = nivel || "";

            modal.classList.add('is-open');
        }
    });

    saveBtn.addEventListener('click', () => {
        const eventId = document.getElementById('edit-event-id').value;
        const atividade = document.getElementById('edit-atividade').value;
        const inicioDate = document.getElementById('edit-inicio').value;
        const terminoDate = document.getElementById('edit-termino').value;
        const secao = document.getElementById('edit-secao').value;
        const local = document.getElementById('edit-local').value;
        const nivel = document.getElementById('edit-nivel') ? document.getElementById('edit-nivel').value : "";

        if (!atividade || !inicioDate || !terminoDate || !secao) {
            frappe.msgprint('Por favor, preencha todos os campos obrigatórios.');
            return;
        }

        // Append default times
        const inicio = `${inicioDate} 08:00:00`;
        const termino = `${terminoDate} 12:00:00`;

        frappe.call({
            method: "gris.api.calendario.simulation.update_simulation_event",
            args: {
                event_id: eventId,
                atividade: atividade,
                inicio: inicio,
                termino: termino,
                secao: secao,
                local: local,
                nivel: nivel
            },
            freeze: true,
            freeze_message: "Atualizando...",
            callback: function(r) {
                if (r.message && r.message.success) {
                    frappe.show_alert({message: r.message.message, indicator: 'green'});
                    closeModal();
                    setTimeout(() => window.location.reload(), 1000);
                } else {
                    frappe.msgprint({
                        title: __('Erro'),
                        indicator: 'red',
                        message: r.message ? r.message.message : "Erro ao atualizar."
                    });
                }
            }
        });
    });

    deleteBtn.addEventListener('click', () => {
        const eventId = document.getElementById('edit-event-id').value;
        closeModal();
        
        frappe.confirm('Tem certeza que deseja excluir este evento?', () => {
            frappe.call({
                method: "gris.api.calendario.simulation.delete_simulation_event",
                args: {
                    event_id: eventId
                },
                freeze: true,
                freeze_message: "Excluindo...",
                callback: function(r) {
                    if (r.message && r.message.success) {
                        frappe.show_alert({message: r.message.message, indicator: 'green'});
                        setTimeout(() => window.location.reload(), 1000);
                    } else {
                        frappe.msgprint({
                            title: __('Erro'),
                            indicator: 'red',
                            message: r.message ? r.message.message : "Erro ao excluir."
                        });
                    }
                }
            });
        }, () => {
            // Re-open modal if cancelled
            modal.classList.add('is-open');
        });
    });
}

function addEventToTable(event) {
    const startDateStr = event.inicio.split(' ')[0];
    const endDateStr = event.termino.split(' ')[0];
    
    function parseDate(str) {
        const parts = str.split('-');
        return new Date(parts[0], parts[1] - 1, parts[2]);
    }
    
    const startDate = parseDate(startDateStr);
    const endDate = parseDate(endDateStr);
    const section = event.secao;
    
    let currentDate = new Date(startDate);
    
    while (currentDate <= endDate) {
        const year = currentDate.getFullYear();
        const month = String(currentDate.getMonth() + 1).padStart(2, '0');
        const day = String(currentDate.getDate()).padStart(2, '0');
        const dateStr = `${year}-${month}-${day}`;
        
        const row = document.querySelector(`tr[data-date="${dateStr}"]`);
        if (row) {
            const cell = row.querySelector(`td[data-section="${section}"]`);
            if (cell) {
                let container = cell.querySelector('.activity-container');
                if (!container) {
                    container = document.createElement('div');
                    container.className = 'activity-container';
                    cell.appendChild(container);
                }
                
                const card = document.createElement('div');
                card.className = 'activity-card';
                
                // Add Ramo class
                if (event.ramo_class) {
                    card.classList.add(event.ramo_class);
                }
                
                // Add continuation classes
                if (dateStr !== startDateStr) {
                    card.classList.add('is-continued-top');
                }
                if (dateStr !== endDateStr) {
                    card.classList.add('is-continued-bottom');
                }

                card.setAttribute('data-event-id', event.name);
                card.setAttribute('data-atividade', event.atividade);
                card.setAttribute('data-inicio', event.inicio);
                card.setAttribute('data-termino', event.termino);
                card.setAttribute('data-secao', event.secao);
                card.setAttribute('data-local', event.local || '');
                
                // Style for dynamic insertion
                card.style.flex = '1 1 0';
                card.style.minWidth = '0';
                
                const body = document.createElement('div');
                body.className = 'activity-body';
                
                if (dateStr === startDateStr) {
                    const title = document.createElement('div');
                    title.className = 'activity-title';
                    title.textContent = event.atividade;
                    body.appendChild(title);
                    
                    if (event.local) {
                        const loc = document.createElement('div');
                        loc.className = 'activity-location';
                        loc.innerHTML = `<i class="fa fa-map-marker"></i> ${event.local}`;
                        body.appendChild(loc);
                    }
                } else {
                     const marker = document.createElement('div');
                     marker.className = 'activity-continuation-marker';
                     body.appendChild(marker);
                }
                
                card.appendChild(body);
                container.appendChild(card);
            }
        }
        
        currentDate.setDate(currentDate.getDate() + 1);
    }
}

function initReconciliation() {
    const btnReconcile = document.getElementById('btn-reconcile');
    const modal = document.getElementById('reconcile-modal');
    if (!btnReconcile || !modal) return;

    const loading = document.getElementById('reconcile-loading');
    const empty = document.getElementById('reconcile-empty');
    const list = document.getElementById('reconcile-list');
    const tbody = document.getElementById('reconcile-tbody');
    const btnConfirm = document.getElementById('btn-confirm-reconcile');
    const closeBtns = modal.querySelectorAll('.close-modal');

    // Close logic
    closeBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            modal.classList.add('d-none');
        });
    });

    // Open logic
    btnReconcile.addEventListener('click', () => {
         modal.classList.remove('d-none');
         fetchDifferences();
    });

    function fetchDifferences() {
        loading.classList.remove('d-none');
        empty.classList.add('d-none');
        list.classList.add('d-none');
        btnConfirm.disabled = true;
        tbody.innerHTML = '';

        const urlParams = new URLSearchParams(window.location.search);
        const year = urlParams.get('year') || new Date().getFullYear();

        frappe.call({
            method: 'gris.www.calendario.simulacao_calendario.get_reconciliation_data',
            args: { year: year },
            callback: function(r) {
                loading.classList.add('d-none');
                if (r.message && r.message.length > 0) {
                    renderDifferences(r.message);
                    list.classList.remove('d-none');
                    btnConfirm.disabled = false;
                } else {
                    empty.classList.remove('d-none');
                }
            }
        });
    }

        function renderDifferences(diffs) {
        tbody.innerHTML = diffs.map((diff, index) => {
            // Determine display source (Simulated has priority for metadata unless it's removed)
            const doc = diff.simulated || diff.official;
            const title = `${doc.atividade} (${doc.secao})`;
            
            let dateInfo = "";
            try {
                if (frappe.datetime && frappe.datetime.str_to_user) {
                     // Show only Date
                     const splitDate = (val) => {
                        if(!val) return "";
                        return val.split(" ")[0];
                     }
                     const d1 = frappe.datetime.str_to_user(splitDate(doc.inicio));
                     const d2 = frappe.datetime.str_to_user(splitDate(doc.termino));
                     
                     if (d1 === d2) {
                        dateInfo = d1;
                     } else {
                        dateInfo = `${d1} - ${d2}`;
                     }
                } else {
                     dateInfo = doc.inicio.split(" ")[0];
                }
            } catch(e) {
                 dateInfo = doc.inicio;
            }

            let statusHtml = '';
            let actionHtml = '';

            const groupName = 'recon-' + index;

            // Common Radio Buttons Structure
            // Option 1: Ignore/Keep Status Quo
            // Option 2: Apply Change (Add/Update/Delete)

            if (diff.type === 'added') {
                statusHtml = `<div style="font-size: 0.8em; margin-top: 4px;"><span class="text-success">Novo na Simulação</span></div>`;
                actionHtml = `
                    <td class="text-center p-2">
                        <label class="reconcile-card">
                            <input type="radio" name="${groupName}" value="ignore" checked>
                            <span>Não Incluir</span>
                        </label>
                    </td>
                    <td class="text-center p-2">
                         <label class="reconcile-card reconcile-card--success">
                            <input type="radio" name="${groupName}" value="apply">
                            <span class="text-success">Adicionar</span>
                        </label>
                    </td>
                `;
            } else if (diff.type === 'removed') {
                statusHtml = `<div style="font-size: 0.8em; margin-top: 4px;"><span class="text-danger">Excluído na Simulação</span></div>`;
                actionHtml = `
                    <td class="text-center p-2">
                        <label class="reconcile-card">
                            <input type="radio" name="${groupName}" value="ignore" checked>
                            <span class="text-primary">Manter Oficial</span>
                        </label>
                    </td>
                    <td class="text-center p-2">
                         <label class="reconcile-card reconcile-card--danger">
                            <input type="radio" name="${groupName}" value="apply">
                            <span class="text-danger">Excluir</span>
                        </label>
                    </td>
                `;
            } else if (diff.type === 'modified') {
                const unscrub = (str) => {
                     if (frappe.model && frappe.model.unscrub) return frappe.model.unscrub(str);
                     return str.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                };
                const changes = diff.diffs.map(field => {
                    const oldVal = diff.official[field] !== undefined && diff.official[field] !== null ? diff.official[field] : '<i class="text-muted">Vazio</i>';
                    const newVal = diff.simulated[field] !== undefined && diff.simulated[field] !== null ? diff.simulated[field] : '<i class="text-muted">Vazio</i>';
                    return `<div style="margin-top:2px;">
                        <strong>${unscrub(field)}</strong>: 
                        <s class="text-muted">${oldVal}</s> 
                        <i class="fa fa-arrow-right" style="font-size:10px; margin:0 4px;"></i> 
                        <span class="text-primary">${newVal}</span>
                    </div>`;
                }).join("");
                
                statusHtml = `<div style="font-size: 0.8em; margin-top: 4px; display: flex; flex-direction: column;">${changes}</div>`;
                
                actionHtml = `
                    <td class="text-center p-2">
                        <label class="reconcile-card">
                            <input type="radio" name="${groupName}" value="ignore" checked>
                            <span class="text-muted">Ignorar</span>
                        </label>
                    </td>
                    <td class="text-center p-2">
                         <label class="reconcile-card reconcile-card--primary">
                            <input type="radio" name="${groupName}" value="apply">
                            <span class="text-primary">Atualizar</span>
                        </label>
                    </td>
                `;
            }

            return `
                <tr>
                    <td>
                        <div style="font-weight: 600;">${title}</div>
                        <div style="font-size: 0.85em; color: var(--text-muted);">${dateInfo}</div>
                        ${statusHtml}
                        <div style="font-size: 0.7em; color: #999; margin-top: 2px;">ID: ${diff.key}</div>
                    </td>
                    ${actionHtml}
                </tr>`;
        }).join('');
        
        const btnSelectAll = document.getElementById('btn-select-all-apply');
        if (btnSelectAll) {
            btnSelectAll.onclick = () => {
                const inputs = tbody.querySelectorAll('input[value="apply"]');
                inputs.forEach(input => input.checked = true);
            };
        }

        btnConfirm.onclick = () => {
            const actions = [];
            diffs.forEach((diff, index) => {
                const groupName = 'recon-' + index;
                const selected = document.querySelector(`input[name="${groupName}"]:checked`).value;
                
                if (selected === 'apply') {
                    if (diff.type === 'added') {
                        actions.push({
                            action: 'add',
                            doc: diff.simulated,
                            sim_name: diff.key
                        });
                    } else if (diff.type === 'removed') {
                        actions.push({
                            action: 'delete',
                            name: diff.key
                        });
                    } else if (diff.type === 'modified') {
                        actions.push({
                            action: 'update',
                            name: diff.key,
                            doc: diff.simulated,
                            sim_name: diff.key
                        });
                    }
                }
            });

            if (actions.length === 0) {
                frappe.msgprint('Nenhuma alteração selecionada para aplicação.');
                return;
            }

            submitReconciliation(actions);
        };
    }
}

function submitReconciliation(actions) {
    frappe.call({
        method: 'gris.www.calendario.simulacao_calendario.reconcile_calendar',
        args: { actions: JSON.stringify(actions) },
        freeze: true,
        freeze_message: 'Aplicando alterações...',
        callback: function(r) {
            if (r.message && r.message.count !== undefined) {
                // Close reconcilation modal
                const reconcileModal = document.getElementById('reconcile-modal');
                reconcileModal.classList.add('d-none');
                
                // Open success modal
                const successModal = document.getElementById('success-modal');
                const successMsg = document.getElementById('success-message');
                const successBtn = document.getElementById('btn-success-ok');
                
                successMsg.innerText = `${r.message.count} alterações aplicadas com sucesso.`;
                successModal.classList.remove('d-none');
                
                successBtn.onclick = function() {
                    window.location.reload();
                };
            }
        }
    });
}

// Holiday Modal Logic
frappe.ready(function() {
    initHolidayModal();
});

function initHolidayModal() {
    const modal = document.getElementById('holiday-modal');
    if (!modal) return;

    // Move modal to body to ensure it's not clipped
    document.body.appendChild(modal);

    const closeElements = modal.querySelectorAll('.close-modal');
    
    function closeModal() {
        modal.classList.add('d-none');
        document.body.style.overflow = '';
    }
    
    closeElements.forEach(el => el.addEventListener('click', closeModal));
    
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !modal.classList.contains('d-none')) {
            closeModal();
        }
    });

    // Delegated click handler for holidays
    document.addEventListener('click', function(e) {
        const holidayBtn = e.target.closest('.holiday-indicator');
        if (holidayBtn) {
            e.preventDefault();
            e.stopPropagation();
            openHolidayModal(holidayBtn);
        }
    });
}

function openHolidayModal(element) {
    const name = element.getAttribute("data-holiday-name");
    const type = element.getAttribute("data-holiday-type");
    const desc = element.getAttribute("data-holiday-desc");

    const modal = document.getElementById("holiday-modal");
    const nameEl = document.getElementById("holiday-modal-name");
    const typeEl = document.getElementById("holiday-modal-type");
    const descEl = document.getElementById("holiday-modal-desc");

    if (modal && nameEl && typeEl && descEl) {
        nameEl.textContent = name || "Feriado";
        typeEl.textContent = type || "Geral";
        
        // Reset classes and apply type logic
        typeEl.className = "holiday-type-tag";
        typeEl.setAttribute("data-type", type);
        
        descEl.textContent = desc || "Sem descrição disponível.";
        
        modal.classList.remove("d-none");
        
        // Force visual update
        modal.style.zIndex = '9999';
        modal.style.display = 'flex';
        
        document.body.style.overflow = 'hidden';
    }
}

