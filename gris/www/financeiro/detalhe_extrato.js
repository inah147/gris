document.addEventListener('DOMContentLoaded', function() {
	const TRANSFER_CATEGORIES = new Set([
		'Transferência entre Contas',
		'Transferência entre Carteiras'
	]);

	const btnSalvar = document.getElementById('btn-salvar-extrato');
	const footerSalvar = document.getElementById('footer-salvar');
	let initialData = {};

	// Lista de campos editáveis
	const editableFields = [
		'descricao',
		'descricao_reduzida',
		'categoria',
		'centro_de_custo',
		'ordinaria_extraordinaria',
		'conta_fixa',
		'beneficiario',
		'repasse_entre_contas',
		'transacao_revisada',
		'observacoes'
	];

	// Função para mostrar/ocultar campos baseado na categoria
	function toggleConditionalFields() {
		const categoriaSelect = document.querySelector('[name="categoria"]');
		const beneficiarioContainer = document.getElementById('beneficiario-field-container');
		const contaFixaContainer = document.getElementById('conta-fixa-field-container');
		const repasseEntreContas = document.getElementById('repasse_entre_contas');
		
		if (categoriaSelect) {
			const categoria = categoriaSelect.value;
			const isTransferCategory = TRANSFER_CATEGORIES.has(categoria);
			
			// Campo Beneficiário: só aparece se categoria = "Contribuição Mensal"
			if (beneficiarioContainer) {
				if (categoria === 'Contribuição Mensal') {
					beneficiarioContainer.style.display = '';
				} else {
					beneficiarioContainer.style.display = 'none';
				}
			}
			
			// Campo Conta Fixa: só aparece se categoria = "Contas Ordinárias"
			if (contaFixaContainer) {
				if (categoria === 'Contas Ordinárias') {
					contaFixaContainer.style.display = '';
				} else {
					contaFixaContainer.style.display = 'none';
				}
			}

			if (repasseEntreContas) {
				repasseEntreContas.checked = isTransferCategory;
				repasseEntreContas.disabled = true;
			}
		}
	}

	// Executa ao carregar a página
	toggleConditionalFields();

	// Adiciona listener no campo categoria
	const categoriaSelect = document.querySelector('[name="categoria"]');
	if (categoriaSelect) {
		categoriaSelect.addEventListener('change', toggleConditionalFields);
	}

	// Seleciona todos os campos editáveis na página (não só dentro do form)
	function getFieldElement(field) {
		return document.querySelector(`[name="${field}"]`);
	}

	function getFormData() {
		const data = {};
		editableFields.forEach(field => {
			const el = getFieldElement(field);
			if (!el) return;
			if (el.type === 'checkbox') {
				data[field] = el.checked ? '1' : '0';
			} else {
				data[field] = el.value;
			}
		});
		return data;
	}

	function normalizeDocname(value) {
		if (!value) {
			return '';
		}
		const raw = String(value);
		try {
			return raw.includes('%') ? decodeURIComponent(raw) : raw;
		} catch (e) {
			return raw;
		}
	}

	// Salva o estado inicial
	initialData = getFormData();

	// Detecta mudanças em campos editáveis
	editableFields.forEach(field => {
		const el = getFieldElement(field);
		if (!el) return;
		el.addEventListener('input', function() {
			const current = getFormData();
			let changed = false;
			for (let k in current) {
				if (current[k] !== initialData[k]) {
					changed = true;
					break;
				}
			}
			if (changed) {
				footerSalvar.style.display = 'flex';
			} else {
				footerSalvar.style.display = 'none';
			}
		});
		// Para checkbox, também escuta 'change'
		if (el.type === 'checkbox') {
			el.addEventListener('change', function() {
				const current = getFormData();
				let changed = false;
				for (let k in current) {
					if (current[k] !== initialData[k]) {
						changed = true;
						break;
					}
				}
				if (changed) {
					footerSalvar.style.display = 'flex';
				} else {
					footerSalvar.style.display = 'none';
				}
			});
		}
	});

	// Salvar alterações
	btnSalvar.addEventListener('click', function() {
		btnSalvar.disabled = true;
		btnSalvar.textContent = 'Salvando...';
		const data = getFormData();
		const qsDocname = new URLSearchParams(window.location.search).get('name');
		const docname = normalizeDocname(
			(window.frappe && frappe.form_dict && frappe.form_dict.name) || qsDocname
		);
		if (!docname) {
			alert('ID do documento não encontrado.');
			btnSalvar.disabled = false;
			btnSalvar.textContent = 'Salvar';
			return;
		}
		frappe.call({
			method: 'frappe.client.get',
			args: {
				doctype: 'Transacao Extrato Geral',
				name: docname
			},
			callback: function(r) {
				if (r.message) {
					let doc = r.message;
					Object.assign(doc, data);
					frappe.call({
						method: 'frappe.client.save',
						args: { doc },
						callback: function(res) {
							if (!res.exc) {
								initialData = getFormData();
								footerSalvar.style.display = 'none';
								frappe.show_alert('Alterações salvas com sucesso!');
							} else {
								frappe.show_alert({message: 'Erro ao salvar: ' + res.exc, indicator: 'red'});
							}
							btnSalvar.disabled = false;
							btnSalvar.textContent = 'Salvar';
						}
					});
				} else {
					frappe.show_alert({message: 'Erro ao buscar documento.', indicator: 'red'});
					btnSalvar.disabled = false;
					btnSalvar.textContent = 'Salvar';
				}
			}
		});
	});
});
// Arquivo JS para página de detalhe de extrato
// Adicione scripts customizados aqui, se necessário

// Exemplo: highlight de campo, eventos, etc.
