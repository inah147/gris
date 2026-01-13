frappe.ready(function() {
	if ($('#meus-dados-form').length > 0) {
		
		// Handle adding skills
		$('#btn-add-habilidade').on('click', function() {
			addHabilidade();
		});

		$('#nova-habilidade').on('keypress', function(e) {
			if (e.which === 13) {
				e.preventDefault();
				addHabilidade();
			}
		});

		$(document).on('click', '.remove-habilidade', function() {
			$(this).closest('.habilidade-tag').remove();
		});

		function addHabilidade() {
			const val = $('#nova-habilidade').val().trim();
			if (val) {
				const badge = `
					<span class="g-badge g-badge--primary me-1 mb-1 habilidade-tag">
						${val}
						<span class="remove-habilidade" style="cursor:pointer; margin-left:5px;">&times;</span>
					</span>
				`;
				$('.habilidades-list').append(badge);
				$('#nova-habilidade').val('');
			}
		}

		// Handle form submit
		$('#meus-dados-form').on('submit', function(e) {
			e.preventDefault();
			
			const o_que_gosta = $('#o_que_gosta').val();
			const habilidades = [];
			$('.habilidade-tag').each(function() {
				// Get text excluding the remove 'x'
				habilidades.push($(this).contents().filter(function() {
					return this.nodeType === 3;
				}).text().trim());
			});

			frappe.call({
				method: "gris.www.responsavel.meus_dados.update_meus_dados",
				args: {
					o_que_gosta_de_fazer_no_dia_a_dia: o_que_gosta,
					habilidades: JSON.stringify(habilidades)
				},
				freeze: true,
				callback: function(r) {
					if (!r.exc) {
						frappe.msgprint("Dados atualizados com sucesso.");
					}
				}
			});
		});
	}
});
