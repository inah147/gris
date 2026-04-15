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

	// --- Modal Adicionar Beneficiário ---
	const btnAdicionar = document.getElementById('btn-adicionar-beneficiario');
	const modalAdicionar = document.getElementById('modalAdicionar');
	const backdropAdicionar = document.getElementById('modalAdicionarBackdrop');
	const btnConfirmarAdicionar = document.getElementById('btn-confirmar-adicionar');
	const formAdicionar = document.getElementById('form-adicionar-beneficiario');
	const inputNome = document.getElementById('add_nome_jovem');
	const inputCpf = document.getElementById('add_cpf_jovem');
	const inputDataNasc = document.getElementById('add_data_nascimento_jovem');
	const responsavelCpf = (document.getElementById('responsavel-data')?.dataset.cpf || '').replace(/\D/g, '');

	if (btnAdicionar) {
		btnAdicionar.addEventListener('click', function() {
			openModalAdicionar();
		});
	}

	if (btnConfirmarAdicionar) {
		btnConfirmarAdicionar.addEventListener('click', function() {
			submitAdicionarBeneficiario();
		});
	}

	// Máscara de CPF para o campo do modal
	if (inputCpf) {
		inputCpf.addEventListener('input', function() {
			let value = this.value.replace(/\D/g, '');
			if (value.length > 11) value = value.slice(0, 11);
			if (value.length > 9) {
				value = value.replace(/^(\d{3})(\d{3})(\d{3})(\d{1,2}).*/, '$1.$2.$3-$4');
			} else if (value.length > 6) {
				value = value.replace(/^(\d{3})(\d{3})(\d{1,3}).*/, '$1.$2.$3');
			} else if (value.length > 3) {
				value = value.replace(/^(\d{3})(\d{1,3}).*/, '$1.$2');
			}
			this.value = value;
		});
	}

	function openModalAdicionar() {
		if (formAdicionar) formAdicionar.reset();
		clearValidation();
		if (modalAdicionar && backdropAdicionar) {
			modalAdicionar.style.display = 'block';
			backdropAdicionar.style.display = 'block';
			setTimeout(() => {
				modalAdicionar.classList.add('show');
				backdropAdicionar.classList.add('show');
			}, 10);
		}
	}

	function closeModalAdicionar() {
		if (modalAdicionar && backdropAdicionar) {
			modalAdicionar.classList.remove('show');
			backdropAdicionar.classList.remove('show');
			setTimeout(() => {
				modalAdicionar.style.display = 'none';
				backdropAdicionar.style.display = 'none';
			}, 300);
		}
	}

	function clearValidation() {
		if (formAdicionar) {
			formAdicionar.querySelectorAll('.is-invalid').forEach(el => el.classList.remove('is-invalid'));
		}
	}

	function validateCPF(cpf) {
		cpf = cpf.replace(/\D/g, '');
		if (cpf.length !== 11) return false;
		if (/^(\d)\1{10}$/.test(cpf)) return false;
		let sum = 0;
		for (let i = 0; i < 9; i++) sum += parseInt(cpf.charAt(i)) * (10 - i);
		let remainder = 11 - (sum % 11);
		if (remainder === 10 || remainder === 11) remainder = 0;
		if (remainder !== parseInt(cpf.charAt(9))) return false;
		sum = 0;
		for (let i = 0; i < 10; i++) sum += parseInt(cpf.charAt(i)) * (11 - i);
		remainder = 11 - (sum % 11);
		if (remainder === 10 || remainder === 11) remainder = 0;
		return remainder === parseInt(cpf.charAt(10));
	}

	function validateAdicionarForm() {
		clearValidation();
		let valid = true;

		const nome = (inputNome.value || '').trim();
		if (!nome || !/^[A-Za-zÀ-ÿ\s]+$/.test(nome)) {
			inputNome.classList.add('is-invalid');
			valid = false;
		}

		const cpfValue = (inputCpf.value || '').trim();
		if (!validateCPF(cpfValue)) {
			inputCpf.classList.add('is-invalid');
			valid = false;
		} else {
			const cpfLimpo = cpfValue.replace(/\D/g, '');
			if (responsavelCpf && cpfLimpo === responsavelCpf) {
				inputCpf.classList.add('is-invalid');
				inputCpf.nextElementSibling.textContent = 'O CPF do jovem não pode ser o mesmo do responsável.';
				valid = false;
			}
		}

		const dataNasc = inputDataNasc.value;
		if (!dataNasc || new Date(dataNasc) >= new Date(new Date().toISOString().split('T')[0])) {
			inputDataNasc.classList.add('is-invalid');
			valid = false;
		}

		return valid;
	}

	function submitAdicionarBeneficiario() {
		if (!validateAdicionarForm()) return;

		frappe.call({
			method: 'gris.www.responsavel.beneficiarios.adicionar_beneficiario',
			args: {
				nome_jovem: inputNome.value.trim(),
				cpf_jovem: inputCpf.value.trim(),
				data_nascimento_jovem: inputDataNasc.value
			},
			freeze: true,
			freeze_message: 'Adicionando beneficiário...',
			callback: function(r) {
				if (r.message && r.message.ok) {
					closeModalAdicionar();
					frappe.msgprint(r.message.message || 'Beneficiário adicionado com sucesso!');
					setTimeout(() => { window.location.reload(); }, 1500);
				}
			}
		});
	}

	// Close handlers for adicionar modal
	if (backdropAdicionar) {
		backdropAdicionar.addEventListener('click', closeModalAdicionar);
	}
	
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
		btn.addEventListener('click', function() {
			closeModal();
			closeModalAdicionar();
		});
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
