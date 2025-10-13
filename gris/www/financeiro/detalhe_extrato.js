document.addEventListener('DOMContentLoaded', function() {
	const btnSalvar = document.getElementById('btn-salvar-extrato');
	let initialData = {};

	// Lista de campos editáveis
	const editableFields = [
		'descricao_reduzida',
		'descricao',
		'categoria',
		'centro_de_custo',
		'fixo_variavel',
		'ordinaria_extraordinaria',
		'conta_fixa',
		'beneficiario',
		'observacoes',
		'repasse_entre_contas',
		'transacao_revisada'
	];

	// Função para mostrar/ocultar campo de beneficiário baseado na categoria
	function toggleBeneficiarioField() {
		const categoriaSelect = document.querySelector('[name="categoria"]');
		const beneficiarioContainer = document.getElementById('beneficiario-field-container');
		
		if (categoriaSelect && beneficiarioContainer) {
			const categoria = categoriaSelect.value;
			if (categoria === 'Contribuição Mensal') {
				beneficiarioContainer.style.display = '';
			} else {
				beneficiarioContainer.style.display = 'none';
			}
		}
	}

	// Executa ao carregar a página
	toggleBeneficiarioField();

	// Adiciona listener no campo categoria
	const categoriaSelect = document.querySelector('[name="categoria"]');
	if (categoriaSelect) {
		categoriaSelect.addEventListener('change', toggleBeneficiarioField);
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
			btnSalvar.classList.toggle('d-none', !changed);
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
				btnSalvar.classList.toggle('d-none', !changed);
			});
		}
	});

	// Salvar alterações
	btnSalvar.addEventListener('click', function() {
		btnSalvar.disabled = true;
		btnSalvar.textContent = 'Salvando...';
		const data = getFormData();
		const docname = (window.frappe && frappe.form_dict && frappe.form_dict.name) || (window.location.search.match(/name=([^&]+)/) || [])[1];
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
								btnSalvar.classList.add('d-none');
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
