frappe.ready(function() {
    scrollToToday();
    initFilters();
    initHoverEffects();
    initModal();
});

let currentVisitId = null;

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
    
    function applyFilters() {
        const selectedSections = Array.from(sectionCheckboxes)
            .filter(cb => cb.checked)
            .map(cb => cb.value);
        
        const showEmptyDays = showEmptyDaysCheckbox.checked;
            
        const rows = document.querySelectorAll('.calendar-row');
        
        rows.forEach(row => {
            let showRow = false;
            
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
            
            if (showRow) {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        });

        // Handle month separators
        document.querySelectorAll('.month-separator-row').forEach(sep => {
            sep.style.display = '';
        });
        
        // Also toggle column visibility
        const allSections = Array.from(sectionCheckboxes).map(cb => cb.value);
        const unselectedSections = allSections.filter(s => !selectedSections.includes(s));
        
        // Show all first
        document.querySelectorAll('.col-section, .col-activity').forEach(el => el.style.display = '');
        
        unselectedSections.forEach(section => {
             const selector = `[data-section="${CSS.escape(section)}"]`;
             // Hide cells
             document.querySelectorAll(`td${selector}`).forEach(el => el.style.display = 'none');
             
             // Hide headers
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

function initModal() {
    const modal = document.getElementById('visit-modal');
    const modalBackdrop = document.getElementById('visit-modal-backdrop');
    const rescheduleModal = document.getElementById('reschedule-modal');
    const rescheduleBackdrop = document.getElementById('reschedule-modal-backdrop');
    
    let selectedRescheduleDate = null;

    // Open Modal
    document.querySelectorAll('.visit-card').forEach(card => {
        card.addEventListener('click', (e) => {
            e.stopPropagation();
            currentVisitId = card.getAttribute('data-event-id');
            const name = card.getAttribute('data-name');
            const age = card.getAttribute('data-age');
            const jovemId = card.getAttribute('data-jovem');
            const confirmed = card.getAttribute('data-confirmed') === '1';
            
            document.getElementById('modal-child-name').textContent = name;
            document.getElementById('modal-child-age').textContent = age;
            document.getElementById('btn-open-file').href = `/recepcao/ficha_registro?name=${jovemId}`;
            
            const statusContainer = document.getElementById('modal-status-container');
            const btnConfirm = document.getElementById('btn-confirm');
            const btnUnconfirm = document.getElementById('btn-unconfirm');
            
            if (confirmed) {
                statusContainer.style.display = 'flex';
                btnConfirm.style.display = 'none';
                btnUnconfirm.style.display = 'block';
            } else {
                statusContainer.style.display = 'none';
                btnConfirm.style.display = 'block';
                btnUnconfirm.style.display = 'none';
            }
            
            openModal(modal, modalBackdrop);
        });
    });
    
    // Close Modal Functions
    window.closeVisitModal = function() {
        closeModal(modal, modalBackdrop);
        currentVisitId = null;
    }
    
    window.closeRescheduleModal = function() {
        closeModal(rescheduleModal, rescheduleBackdrop);
        selectedRescheduleDate = null;
    }
    
    function openModal(el, backdrop) {
        el.style.display = 'flex';
        backdrop.style.display = 'block';
        // Force reflow
        el.offsetHeight;
        
        setTimeout(() => {
            el.classList.add('show');
            backdrop.classList.add('show');
            document.body.classList.add('modal-open');
        }, 10);
    }

    function closeModal(el, backdrop) {
        el.classList.remove('show');
        backdrop.classList.remove('show');
        document.body.classList.remove('modal-open');
        setTimeout(() => {
            el.style.display = 'none';
            backdrop.style.display = 'none';
        }, 300);
    }
    
    // Close on backdrop click
    modalBackdrop.addEventListener('click', closeVisitModal);
    rescheduleBackdrop.addEventListener('click', closeRescheduleModal);
    
    // Actions
    document.getElementById('btn-confirm').addEventListener('click', () => {
        if (!currentVisitId) return;
        
        frappe.call({
            method: 'gris.www.recepcao.agenda_visitas.confirm_visit',
            args: { visit_name: currentVisitId },
            callback: function(r) {
                if (!r.exc) {
                    frappe.show_alert({message: 'Visita confirmada com sucesso!', indicator: 'green'});
                    
                    // Update UI without reload
                    const card = document.querySelector(`.visit-card[data-event-id="${currentVisitId}"]`);
                    if (card) {
                        card.setAttribute('data-confirmed', '1');
                        card.classList.add('visit-confirmed');
                        // Check if icon exists, if not add it
                        if (!card.querySelector('.visit-status-icon')) {
                            // Append directly to card for absolute positioning
                            const icon = document.createElement('i');
                            icon.className = 'fa fa-check visit-status-icon';
                            icon.title = 'Confirmada';
                            card.appendChild(icon);
                        }
                    }
                    
                    closeVisitModal();
                }
            }
        });
    });

    document.getElementById('btn-unconfirm').addEventListener('click', () => {
        if (!currentVisitId) return;
        
        frappe.call({
            method: 'gris.www.recepcao.agenda_visitas.unconfirm_visit',
            args: { visit_name: currentVisitId },
            callback: function(r) {
                if (!r.exc) {
                    frappe.show_alert({message: 'Confirmação removida.', indicator: 'orange'});
                    
                    // Update UI without reload
                    const card = document.querySelector(`.visit-card[data-event-id="${currentVisitId}"]`);
                    if (card) {
                        card.setAttribute('data-confirmed', '0');
                        card.classList.remove('visit-confirmed');
                        const icon = card.querySelector('.visit-status-icon');
                        if (icon) icon.remove();
                    }
                    
                    closeVisitModal();
                }
            }
        });
    });
    
    document.getElementById('btn-cancel').addEventListener('click', () => {
        if (!currentVisitId) return;
        
        frappe.call({
            method: 'gris.www.recepcao.agenda_visitas.cancel_visit',
            args: { visit_name: currentVisitId },
            callback: function(r) {
                if (!r.exc) {
                    frappe.show_alert({message: 'Visita cancelada.', indicator: 'orange'});
                    
                    // Update UI without reload
                    const card = document.querySelector(`.visit-card[data-event-id="${currentVisitId}"]`);
                    if (card) card.remove();
                    
                    closeVisitModal();
                }
            }
        });
    });
    
    document.getElementById('btn-reschedule').addEventListener('click', () => {
        // Close visit modal first
        modal.classList.remove('show');
        modalBackdrop.classList.remove('show');
        setTimeout(() => {
             modal.style.display = 'none';
             modalBackdrop.style.display = 'none';
             
             // Open reschedule modal
             openModal(rescheduleModal, rescheduleBackdrop);
             loadRescheduleDates();
        }, 300);
    });
    
    function loadRescheduleDates() {
        const list = document.getElementById('reschedule-dates-list');
        const btnSave = document.getElementById('btn-save-reschedule');
        
        list.innerHTML = '<div class="text-center p-3">Carregando datas...</div>';
        btnSave.disabled = true;
        selectedRescheduleDate = null;
        
        frappe.call({
            method: 'gris.www.recepcao.agenda_visitas.get_available_visit_dates_for_reschedule',
            args: { visit_name: currentVisitId },
            callback: function(r) {
                if (r.message && r.message.length > 0) {
                    let html = '';
                    r.message.forEach(item => {
                        html += `
                            <button type="button" class="list-group-item list-group-item-action date-option" data-date="${item.value}">
                                ${item.label}
                            </button>
                        `;
                    });
                    list.innerHTML = html;
                    
                    // Add click handlers
                    list.querySelectorAll('.date-option').forEach(btn => {
                        btn.addEventListener('click', function() {
                            list.querySelectorAll('.date-option').forEach(b => b.classList.remove('active'));
                            this.classList.add('active');
                            selectedRescheduleDate = this.getAttribute('data-date');
                            btnSave.disabled = false;
                        });
                    });
                } else {
                    list.innerHTML = '<div class="alert alert-warning">Nenhuma data disponível encontrada nos próximos 60 dias para este ramo.</div>';
                }
            }
        });
    }
    
    document.getElementById('btn-save-reschedule').addEventListener('click', () => {
        if (!selectedRescheduleDate) {
            frappe.msgprint('Por favor, selecione uma data.');
            return;
        }
        
        frappe.call({
            method: 'gris.www.recepcao.agenda_visitas.reschedule_visit',
            args: { visit_name: currentVisitId, new_date: selectedRescheduleDate },
            callback: function(r) {
                if (!r.exc) {
                    frappe.show_alert({message: 'Visita reagendada com sucesso!', indicator: 'green'});
                    
                    // Update UI without reload
                    // For reschedule, we just remove the card from current view as it moved to another date
                    // Ideally we would move it, but that requires finding the target cell which might not be rendered
                    const card = document.querySelector(`.visit-card[data-event-id="${currentVisitId}"]`);
                    if (card) card.remove();
                    
                    closeRescheduleModal();
                }
            }
        });
    });
}

// Schedule Modal Logic
let scheduleAssociates = [];

function openScheduleModal() {
    const modal = document.getElementById('schedule-modal');
    const backdrop = document.getElementById('schedule-modal-backdrop');
    const associateSelect = document.getElementById('schedule-associate');
    const dateSelect = document.getElementById('schedule-date');
    
    // Reset fields
    associateSelect.innerHTML = '<option value="">Carregando...</option>';
    dateSelect.innerHTML = '<option value="">Selecione um associado primeiro</option>';
    dateSelect.disabled = true;
    
    // Show modal
    backdrop.style.display = 'block';
    modal.style.display = 'flex';
    // Force reflow
    modal.offsetHeight;
    modal.classList.add('show');
    
    // Fetch associates
    frappe.call({
        method: 'gris.www.recepcao.agenda_visitas.get_associates_for_scheduling',
        callback: function(r) {
            if (r.message) {
                scheduleAssociates = r.message;
                let html = '<option value="">Selecione...</option>';
                r.message.forEach(assoc => {
                    html += `<option value="${assoc.name}">${assoc.nome_completo} (${assoc.ramo || 'Sem Ramo'})</option>`;
                });
                associateSelect.innerHTML = html;
            } else {
                associateSelect.innerHTML = '<option value="">Nenhum associado disponível</option>';
            }
        }
    });
}

function closeScheduleModal() {
    const modal = document.getElementById('schedule-modal');
    const backdrop = document.getElementById('schedule-modal-backdrop');
    
    modal.classList.remove('show');
    setTimeout(() => {
        modal.style.display = 'none';
        backdrop.style.display = 'none';
    }, 300);
}

// Handle associate selection to load dates
const scheduleAssociateSelect = document.getElementById('schedule-associate');
if (scheduleAssociateSelect) {
    scheduleAssociateSelect.addEventListener('change', function(e) {
        const associateName = e.target.value;
        const dateSelect = document.getElementById('schedule-date');
        
        if (!associateName) {
            dateSelect.innerHTML = '<option value="">Selecione um associado primeiro</option>';
            dateSelect.disabled = true;
            return;
        }
        
        const associate = scheduleAssociates.find(a => a.name === associateName);
        if (!associate || !associate.ramo) {
            dateSelect.innerHTML = '<option value="">Associado sem Ramo definido</option>';
            dateSelect.disabled = true;
            return;
        }
        
        dateSelect.innerHTML = '<option value="">Carregando datas...</option>';
        dateSelect.disabled = true;
        
        frappe.call({
            method: 'gris.www.recepcao.agenda_visitas.get_available_dates_for_ramo',
            args: { ramo: associate.ramo },
            callback: function(r) {
                if (r.message && r.message.length > 0) {
                    let html = '<option value="">Selecione uma data...</option>';
                    r.message.forEach(d => {
                        html += `<option value="${d.value}">${d.label}</option>`;
                    });
                    dateSelect.innerHTML = html;
                    dateSelect.disabled = false;
                } else {
                    dateSelect.innerHTML = '<option value="">Nenhuma data disponível</option>';
                }
            }
        });
    });
}

function confirmSchedule() {
    const associate = document.getElementById('schedule-associate').value;
    const date = document.getElementById('schedule-date').value;
    
    if (!associate || !date) {
        frappe.msgprint('Selecione um associado e uma data.');
        return;
    }
    
    frappe.call({
        method: 'gris.www.recepcao.agenda_visitas.schedule_visit',
        args: {
            associate: associate,
            date: date
        },
        callback: function(r) {
            if (!r.exc) {
                frappe.show_alert({message: 'Visita agendada com sucesso!', indicator: 'green'});
                closeScheduleModal();
                // Reload page to show new visit
                setTimeout(() => window.location.reload(), 1000);
            }
        }
    });
}
