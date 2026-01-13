frappe.ready(function() {
	const btnAgendar = document.getElementById('btn-agendar-visita');
	const modal = document.getElementById('modalAgendamento');
	const backdrop = document.getElementById('modalAgendamentoBackdrop');
	const datesList = document.getElementById('dates-list');
	const btnConfirmar = document.getElementById('btn-confirmar-agendamento');
	const btnReagendar = document.getElementById('btn-reagendar-visita');
	const btnCancelar = document.getElementById('btn-cancelar-visita');
	let selectedDate = null;
	let isReschedule = false;
	
	if (btnAgendar) {
		btnAgendar.addEventListener('click', function() {
			isReschedule = false;
			openModal();
			loadDates();
			if (btnConfirmar) btnConfirmar.disabled = true;
			selectedDate = null;
		});
	}

	if (btnReagendar) {
		btnReagendar.addEventListener('click', function() {
			isReschedule = true;
			openModal();
			loadDates();
			if (btnConfirmar) btnConfirmar.disabled = true;
			selectedDate = null;
		});
	}

	if (btnCancelar) {
		btnCancelar.addEventListener('click', function() {
			frappe.confirm('Tem certeza que deseja cancelar o agendamento?', () => {
				frappe.call({
					method: "gris.www.responsavel.beneficiarios.cancel_visit",
					freeze: true,
					callback: function(r) {
						if (!r.exc) {
							frappe.msgprint("Agendamento cancelado com sucesso.");
							setTimeout(() => {
								window.location.reload();
							}, 1500);
						}
					}
				});
			});
		});
	}

	if (btnConfirmar) {
		btnConfirmar.addEventListener('click', function() {
			if (selectedDate) {
				if (isReschedule) {
					rescheduleVisit(selectedDate);
				} else {
					scheduleVisit(selectedDate);
				}
			}
		});
	}

	// Close modal handlers
	document.querySelectorAll('[data-dismiss-modal]').forEach(btn => {
		btn.addEventListener('click', closeModal);
	});
	
	if (backdrop) {
		backdrop.addEventListener('click', closeModal);
	}

	function openModal() {
		if (modal && backdrop) {
			modal.style.display = 'block';
			backdrop.style.display = 'block';
			setTimeout(() => {
				modal.classList.add('show');
				backdrop.classList.add('show');
			}, 10);
		}
	}

	function closeModal() {
		if (modal && backdrop) {
			modal.classList.remove('show');
			backdrop.classList.remove('show');
			setTimeout(() => {
				modal.style.display = 'none';
				backdrop.style.display = 'none';
			}, 300);
		}
	}

	function loadDates() {
		datesList.innerHTML = '<div class="text-center p-3">Carregando datas...</div>';
		
		frappe.call({
			method: "gris.www.responsavel.beneficiarios.get_available_visit_dates",
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
					datesList.innerHTML = html;
					
					// Add click handlers for dates
					document.querySelectorAll('.date-option').forEach(btn => {
						btn.addEventListener('click', function() {
							// Remove active class from all
							document.querySelectorAll('.date-option').forEach(b => b.classList.remove('active'));
							// Add active class to clicked
							this.classList.add('active');
							
							selectedDate = this.getAttribute('data-date');
							if (btnConfirmar) btnConfirmar.disabled = false;
						});
					});
				} else {
					datesList.innerHTML = '<div class="alert alert-warning">Nenhuma data disponível encontrada nos próximos 2 meses.</div>';
				}
			}
		});
	}

	function scheduleVisit(date) {
		frappe.call({
			method: "gris.www.responsavel.beneficiarios.schedule_visit",
			args: { date: date },
			freeze: true,
			callback: function(r) {
				if (!r.exc) {
					frappe.msgprint("Visita agendada com sucesso!");
					closeModal();
					setTimeout(() => {
						window.location.reload();
					}, 1500);
				}
			}
		});
	}

	function rescheduleVisit(date) {
		frappe.call({
			method: "gris.www.responsavel.beneficiarios.reschedule_visit",
			args: { date: date },
			freeze: true,
			callback: function(r) {
				if (!r.exc) {
					frappe.msgprint("Visita reagendada com sucesso!");
					closeModal();
					setTimeout(() => {
						window.location.reload();
					}, 1500);
				}
			}
		});
	}
});
