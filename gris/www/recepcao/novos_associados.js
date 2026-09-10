// Lista de Novos Associados (/recepcao/novos_associados)
// As linhas vêm de `gris.www.recepcao.novos_associados.listar`: filtrar e paginar troca só
// o corpo da tabela, sem recarregar a página.

(function () {
	const COLSPAN = 10;

	const escapeHtml = (valor) => frappe.utils.escape_html(valor == null ? "" : String(valor));

	const textoOuTraco = (valor) => (valor ? escapeHtml(valor) : "—");

	frappe.ready(() => {
		const form = document.getElementById("novos-filtros");
		const tabela = document.getElementById("novosAssociadosTable");
		const tbody = tabela?.querySelector("tbody");
		const wrapper = document.getElementById("novos-tabela-wrap");
		const carregando = document.getElementById("novos-loading");
		const vazio = document.getElementById("novos-empty");
		const contador = document.getElementById("novos-contador");
		const btnAnterior = document.getElementById("btn-pagina-anterior");
		const btnProxima = document.getElementById("btn-pagina-proxima");
		const btnLimpar = document.getElementById("btn-limpar");

		if (!tbody || !form) return;

		let pagina = 1;
		let ultimaPagina = 1;
		let carregandoAgora = false;

		function filtrosAtuais() {
			const dados = new FormData(form);
			return {
				busca: (dados.get("busca") || "").toString().trim(),
				status: (dados.get("status") || "").toString(),
				ramo: (dados.get("ramo") || "").toString(),
				tipo_de_registro: (dados.get("tipo_de_registro") || "").toString(),
				dados_enviados: (dados.get("dados_enviados") || "").toString(),
			};
		}

		function mostrarEstado(estado) {
			carregando.hidden = estado !== "carregando";
			wrapper.hidden = estado !== "lista";
			vazio.hidden = estado !== "vazio";
		}

		function descreverVazio(comFiltro) {
			const descricao = vazio.querySelector("p");
			if (!descricao) return;
			descricao.textContent = comFiltro
				? "Revise a busca e os filtros aplicados."
				: "Ninguém em integração no momento.";
		}

		function badgeRamo(linha) {
			if (!linha.ramo) return "—";
			return `<span class="badge badge-${escapeHtml(linha.ramo_variante)}">${escapeHtml(
				linha.ramo
			)}</span>`;
		}

		function badgeDados(linha) {
			if (linha.dados_enviados) {
				return '<span class="badge badge-dados-enviados">Enviados</span>';
			}
			return '<span class="badge-outline">Pendentes</span>';
		}

		function acoes(linha) {
			const nome = encodeURIComponent(linha.name);
			const rotuloRegistro = linha.registro_criado_no_paxtu
				? "Formulário do responsável"
				: "Preencher registro em nome do responsável";
			return `
				<div class="novos-acoes">
					<a
						href="/recepcao/ficha_registro?name=${nome}"
						class="btn-sm-outline"
						title="Abrir a ficha de registro"
					>Ficha</a>
					<a
						href="/responsavel/registro?novo_associado=${nome}"
						class="btn-sm-ghost"
						title="${escapeHtml(rotuloRegistro)}"
					>Registro</a>
				</div>`;
		}

		function renderLinhas(linhas) {
			tbody.innerHTML = linhas
				.map((linha) => {
					const nome = encodeURIComponent(linha.name);
					return `
						<tr>
							<td data-coluna="nome">
								<a href="/recepcao/ficha_registro?name=${nome}" class="novos-nome">${escapeHtml(
									linha.nome_completo
								)}</a>
							</td>
							<td>${textoOuTraco(linha.idade)}</td>
							<td>${badgeRamo(linha)}</td>
							<td>${textoOuTraco(linha.status)}</td>
							<td>${textoOuTraco(linha.tipo_de_registro)}</td>
							<td>${badgeDados(linha)}</td>
							<td>${textoOuTraco(linha.responsavel_legal)}</td>
							<td>${textoOuTraco(linha.responsavel_recepcao)}</td>
							<td>${textoOuTraco(linha.atualizado_em)}</td>
							<td>${acoes(linha)}</td>
						</tr>`;
				})
				.join("");
		}

		function renderErro(mensagem) {
			tbody.innerHTML = `
				<tr>
					<td colspan="${COLSPAN}">
						<p class="novos-erro">${escapeHtml(mensagem)}</p>
					</td>
				</tr>`;
			mostrarEstado("lista");
		}

		function atualizarRodape(resposta) {
			const total = Number(resposta.total || 0);
			const porPagina = Number(resposta.por_pagina || 0);
			if (!total) {
				contador.textContent = "Nenhum registro.";
			} else {
				const primeiro = (pagina - 1) * porPagina + 1;
				const ultimo = Math.min(total, primeiro + resposta.linhas.length - 1);
				contador.textContent = `${primeiro}–${ultimo} de ${total} ${
					total === 1 ? "pessoa" : "pessoas"
				}`;
			}
			btnAnterior.disabled = pagina <= 1;
			btnProxima.disabled = pagina >= ultimaPagina;
		}

		function carregar() {
			if (carregandoAgora) return;
			carregandoAgora = true;
			mostrarEstado("carregando");

			frappe.call({
				method: "gris.www.recepcao.novos_associados.listar",
				args: Object.assign({ pagina: pagina }, filtrosAtuais()),
				// O msgprint do Frappe não aparece neste portal: o erro é mostrado na tabela.
				silent: true,
				callback: function (r) {
					const resposta = r.message;
					if (!resposta) {
						renderErro("Não foi possível carregar a lista.");
						return;
					}
					pagina = Number(resposta.pagina || 1);
					ultimaPagina = Number(resposta.ultima_pagina || 1);
					if (resposta.linhas.length) {
						renderLinhas(resposta.linhas);
						mostrarEstado("lista");
					} else {
						tbody.innerHTML = "";
						descreverVazio(Boolean(resposta.com_filtro));
						mostrarEstado("vazio");
					}
					atualizarRodape(resposta);
				},
				error: function () {
					renderErro("Não foi possível carregar a lista. Tente novamente.");
				},
				always: function () {
					carregandoAgora = false;
				},
			});
		}

		form.addEventListener("submit", (evento) => {
			evento.preventDefault();
			pagina = 1;
			carregar();
		});

		btnLimpar?.addEventListener("click", () => {
			// O reset nativo limpa o hidden input do select, mas não o rótulo do trigger.
			window.setTimeout(() => {
				form.querySelectorAll(".select").forEach((el) => {
					el.value = "";
				});
				pagina = 1;
				carregar();
			}, 0);
		});

		btnAnterior.addEventListener("click", () => {
			if (pagina <= 1) return;
			pagina -= 1;
			carregar();
		});

		btnProxima.addEventListener("click", () => {
			if (pagina >= ultimaPagina) return;
			pagina += 1;
			carregar();
		});

		carregar();
	});
})();
