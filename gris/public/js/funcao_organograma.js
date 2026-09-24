/*
 * Dialog "Função no organograma" — período da função, acordos de trabalho voluntário
 * (ATV) e exclusão da linha.
 *
 * Compartilhado pela ficha do associado (/associados/detalhe) e pela página de ATVs
 * (/gestao_adultos/atvs): as duas mexem na mesma linha de `Associado.funcoes_internas`,
 * pelos mesmos endpoints.
 *
 * Marcação e assets vêm de templates/includes/funcao_organograma_dialog.html; a página
 * só chama `window.grisFuncaoOrganograma.abrir(linha, { aoMudar, aoMudarValidade })`.
 *
 * `linha.pessoa` é a chave com espaço de nomes (`associado:<id>` / `responsavel:<id>`);
 * `linha.associado` continua aceito. `linha.comAtv === false` esconde o bloco de
 * acordos, que é documento do quadro e não existe para responsável. `linha.automatica`
 * marca a função mantida pelo cadastro (o Responsável Legal no Conselho): ela não é
 * alocada nem encerrada à mão e não tem acordo a cobrar, então o dialog vira leitura.
 *
 * `aoMudar(funcoes)` recebe a lista nova de funções da pessoa e `aoMudarValidade(linha,
 * validade)` o veredito novo do acordo daquela alocação — é assim que a tabela de quem
 * chamou se atualiza sem recarregar a página.
 */
(function () {
	"use strict";

	const ID = "dialog-funcao-organograma";

	let linhaAtual = null;
	let atvsAtuais = [];
	let aoMudar = null;
	let aoMudarValidade = null;

	// -- Transporte ---------------------------------------------------------

	// `frappe.call` no portal não chama `error` e dispara `always` antes do `callback`:
	// a mensagem do `frappe.throw` se perderia, e é ela que explica o bloqueio.
	async function chamar(metodo, argumentos) {
		const resposta = await fetch(`/api/method/${metodo}`, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				Accept: "application/json",
				"X-Frappe-CSRF-Token": (window.frappe && frappe.csrf_token) || "",
			},
			credentials: "same-origin",
			body: JSON.stringify(argumentos),
		});

		const corpo = await resposta.json().catch(() => ({}));
		if (!resposta.ok) {
			let mensagem = "Não foi possível salvar.";
			try {
				const lista = JSON.parse(corpo._server_messages || "[]");
				if (lista.length) mensagem = JSON.parse(lista[0]).message;
			} catch (e) {
				/* fica a mensagem genérica */
			}
			throw new Error(textoSimples(mensagem));
		}
		return corpo.message;
	}

	function toast(categoria, titulo) {
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: { config: { category: categoria, title: titulo, duration: 4500 } },
			})
		);
	}

	// -- Datas --------------------------------------------------------------

	function paraUsuario(iso) {
		if (!iso) return "";
		const [ano, mes, dia] = String(iso).slice(0, 10).split("-");
		return ano && mes && dia ? `${dia}/${mes}/${ano}` : "";
	}

	/** Lê o datepicker do design system: "aaaa-mm-dd" ou "" quando está vazio.
	 *
	 * O componente expõe `value` como propriedade no elemento raiz; o input escondido é
	 * o reserva para o caso de o script ainda não ter inicializado aquele nó.
	 */
	function dataDe(id) {
		const raiz = campo(id);
		if (!raiz) return "";
		if (typeof raiz.value === "string" || raiz.value === null) {
			return raiz.value || "";
		}
		const escondido = raiz.querySelector("[data-datepicker-value]");
		return (escondido && escondido.value) || "";
	}

	function definirData(id, iso) {
		const raiz = campo(id);
		if (!raiz) return;
		// `value` do datepicker é setter: ele redesenha o rótulo e o calendário.
		raiz.value = iso || null;
	}

	// -- Estado do dialog ---------------------------------------------------

	function dialogo() {
		return document.getElementById(ID);
	}

	function campo(id) {
		return document.getElementById(id);
	}

	function acao(nome) {
		const dlg = dialogo();
		return dlg ? dlg.querySelector(`[data-acao="${nome}"]`) : null;
	}

	function mostrarConfirmacaoDeExclusao(mostrar) {
		const apagar = acao("apagar-funcao");
		const confirmar = acao("apagar-funcao-confirmar");
		const cancelar = acao("apagar-funcao-cancelar");
		if (apagar) apagar.hidden = mostrar;
		if (confirmar) confirmar.hidden = !mostrar;
		if (cancelar) cancelar.hidden = !mostrar;
	}

	/** Chave com espaço de nomes da pessoa da linha aberta. */
	function chaveDaLinha() {
		if (!linhaAtual) return "";
		return (
			linhaAtual.pessoa || (linhaAtual.associado ? `associado:${linhaAtual.associado}` : "")
		);
	}

	/** Tipo e docname separados, para o endpoint de ATV, que só fala de associado. */
	function pessoaDaLinha() {
		const chave = chaveDaLinha();
		if (chave.startsWith("responsavel:")) {
			return { tipo: "responsavel", name: chave.slice("responsavel:".length) };
		}
		return { tipo: "associado", name: chave.replace(/^associado:/, "") };
	}

	/** A função mantida pelo cadastro não tem acordo a cobrar nem ação a oferecer. */
	function automatica(linha) {
		return Boolean((linha || linhaAtual || {}).automatica);
	}

	function mostrarBloco(id, mostrar) {
		const bloco = document.getElementById(id);
		if (bloco) bloco.hidden = !mostrar;
	}

	function preencher(linha) {
		linhaAtual = linha;
		campo("funcao-dialog-nome").textContent = linha.nome || "";
		campo("funcao-dialog-contexto").textContent = [linha.funcao, linha.area]
			.filter(Boolean)
			.join(" · ");
		definirData("funcao-dialog-inicio", linha.data_inicio);
		definirData("funcao-dialog-fim", linha.data_fim);
		preencherEstadoDosBotoes();

		definirData("atv-dialog-inicio", null);
		definirData("atv-dialog-fim", null);
		definirAssinatura(false);
		mostrarConfirmacaoDeExclusao(false);

		const fixa = automatica(linha);
		mostrarBloco("funcao-dialog-aviso-automatica", fixa);
		// Sem alocação para mexer: o período sai do vínculo, não desta tela.
		mostrarBloco("funcao-dialog-acoes-periodo", !fixa);
		mostrarBloco("funcao-dialog-bloco-perigo", !fixa);
		mostrarBloco("funcao-dialog-bloco-atv", linha.comAtv !== false && !fixa);
		renderAtvs(null);
	}

	/** O select do design system também expõe `value`; o hidden é o reserva. */
	function assinaturaEscolhida() {
		const raiz = campo("atv-dialog-assinado");
		if (!raiz) return false;
		const escondido = raiz.querySelector('input[type="hidden"]');
		const valor = escondido ? escondido.value : raiz.value;
		return String(valor) === "1";
	}

	function definirAssinatura(assinado) {
		const raiz = campo("atv-dialog-assinado");
		if (!raiz) return;
		if (typeof raiz.selectByValue === "function") {
			raiz.selectByValue(assinado ? "1" : "0");
			return;
		}
		const escondido = raiz.querySelector('input[type="hidden"]');
		if (escondido) escondido.value = assinado ? "1" : "0";
	}

	function renderAtvs(atvs) {
		const alvo = campo("funcao-dialog-atvs");
		if (!alvo) return;

		atvsAtuais = atvs || [];
		if (atvs === null) {
			alvo.innerHTML = '<p class="funcao-dialog__ajuda">Carregando acordos…</p>';
			return;
		}
		if (!atvs.length) {
			alvo.innerHTML =
				'<p class="funcao-dialog__ajuda">Nenhum acordo cadastrado para esta função.</p>';
			return;
		}

		alvo.innerHTML = `
			<table class="table funcao-dialog__tabela">
				<thead>
					<tr>
						<th scope="col">Início</th>
						<th scope="col">Término</th>
						<th scope="col">Assinado</th>
						${
							/* Sem rótulo: o design system não tem utilitário `sr-only`, e um
						     texto aqui só disputaria espaço com o ícone. */ ""
						}
						<th scope="col" class="funcao-dialog__acoes-celula"></th>
					</tr>
				</thead>
				<tbody>
					${atvs
						.map(
							(atv) => `
						<tr>
							<td>${escapeHtml(paraUsuario(atv.data_inicio))}</td>
							<td>${escapeHtml(paraUsuario(atv.data_fim))}</td>
							<td>
								${
									/* Mesma marcação da macro `switch` do design system. A troca é
									   ouvida em `change`, e não em `click`: o rótulo repassa o
									   clique para o input e o handler dispararia duas vezes. */ ""
								}
								<label class="switch funcao-dialog__switch">
									<input type="checkbox" role="switch" class="input"
										data-acao="alternar-assinatura" data-atv="${escapeHtml(atv.name)}"
										aria-label="Acordo assinado"${atv.assinado ? " checked" : ""}>
								</label>
							</td>
							<td class="funcao-dialog__acoes-celula">
								<button type="button" class="btn-sm-ghost funcao-dialog__apagar-atv"
									data-acao="apagar-atv" data-atv="${escapeHtml(atv.name)}"
									aria-label="Apagar este acordo" title="Apagar este acordo">
									<svg class="ds-lucide ds-lucide--sm" aria-hidden="true" focusable="false" viewBox="0 0 24 24">
										<use href="/assets/gris/design_system/icons/lucide/sprite.svg#trash-2" />
									</svg>
								</button>
							</td>
						</tr>`
						)
						.join("")}
				</tbody>
			</table>`;
	}

	async function carregarAtvs() {
		try {
			const atvs = await chamar("gris.api.gestao_adultos.listar_atvs_da_funcao", {
				associado: pessoaDaLinha().name,
				linha: linhaAtual.linha,
			});
			renderAtvs(atvs || []);
		} catch (erro) {
			renderAtvs([]);
			toast("error", erro.message || String(erro));
		}
	}

	// -- Ações --------------------------------------------------------------

	async function executar(botao, trabalho, sucesso) {
		botao.disabled = true;
		try {
			const resultado = await trabalho();
			if (resultado && resultado.funcoes) {
				// A resposta é a verdade nova sobre a linha: sincronizar o estado local
				// aqui evita que cada ação precise lembrar de atualizar os botões.
				sincronizarLinhaAtual(resultado.funcoes);
				if (typeof aoMudar === "function") {
					aoMudar(resultado.funcoes);
				}
			}
			if (resultado && resultado.atvs) {
				renderAtvs(resultado.atvs);
			}
			if (resultado && resultado.validade && typeof aoMudarValidade === "function") {
				aoMudarValidade(resultado.linha, resultado.validade);
			}
			toast("success", sucesso);
			return resultado;
		} catch (erro) {
			// A mensagem vem do servidor e é o que explica o bloqueio.
			toast("error", erro.message || String(erro));
			return null;
		} finally {
			botao.disabled = false;
		}
	}

	function payloadDaLinha(extra) {
		return {
			payload: JSON.stringify(
				Object.assign({ pessoa: chaveDaLinha(), linha: linhaAtual.linha }, extra || {})
			),
		};
	}

	function salvarPeriodo(botao) {
		const inicio = dataDe("funcao-dialog-inicio");
		const fim = dataDe("funcao-dialog-fim");
		if (!inicio) {
			toast("error", "Informe a data de início da função.");
			return;
		}
		executar(
			botao,
			() =>
				chamar(
					"gris.api.gestao_adultos.editar_funcao",
					payloadDaLinha({ data_inicio: inicio, data_fim: fim })
				),
			"Período atualizado."
		);
	}

	function sincronizarLinhaAtual(funcoes) {
		const nova = funcoes.find((item) => item.linha === linhaAtual.linha);
		if (!nova) {
			// A linha foi apagada; o dialog fecha logo em seguida.
			return;
		}
		Object.assign(linhaAtual, nova);
		definirData("funcao-dialog-inicio", nova.data_inicio);
		definirData("funcao-dialog-fim", nova.data_fim);
		preencherEstadoDosBotoes();
	}

	/** Encerrada não pode ser principal, e já-principal não precisa do botão. */
	function preencherEstadoDosBotoes() {
		const fixa = automatica();
		const principal = acao("principal");
		if (principal) {
			principal.hidden =
				fixa || Boolean(linhaAtual.principal) || Boolean(linhaAtual.data_fim);
		}
		const encerrar = acao("encerrar");
		if (encerrar) encerrar.hidden = fixa || Boolean(linhaAtual.data_fim);
	}

	function adicionarAtv(botao) {
		const inicio = dataDe("atv-dialog-inicio");
		const fim = dataDe("atv-dialog-fim");
		if (!inicio || !fim) {
			toast("error", "Informe o início e o término do acordo.");
			return;
		}
		executar(
			botao,
			() =>
				chamar(
					"gris.api.gestao_adultos.salvar_atv",
					payloadDaLinha({
						data_inicio: inicio,
						data_fim: fim,
						assinado: assinaturaEscolhida() ? 1 : 0,
					})
				),
			"Acordo cadastrado."
		).then((resultado) => {
			if (resultado) {
				definirData("atv-dialog-inicio", null);
				definirData("atv-dialog-fim", null);
				definirAssinatura(false);
			}
		});
	}

	function tratarClique(evento) {
		const dlg = dialogo();
		if (!dlg || !linhaAtual) return;
		const botao = evento.target.closest("[data-acao]");
		if (!botao || !dlg.contains(botao)) return;

		switch (botao.dataset.acao) {
			case "salvar-funcao":
				salvarPeriodo(botao);
				break;
			case "principal":
				executar(
					botao,
					() => chamar("gris.api.gestao_adultos.definir_principal", payloadDaLinha()),
					"Função principal definida."
				);
				break;
			case "encerrar":
				executar(
					botao,
					() => chamar("gris.api.gestao_adultos.encerrar_funcao", payloadDaLinha()),
					"Função encerrada."
				).then((resultado) => {
					if (resultado) dlg.close();
				});
				break;
			case "adicionar-atv":
				adicionarAtv(botao);
				break;
			case "apagar-atv":
				executar(
					botao,
					() =>
						chamar("gris.api.gestao_adultos.apagar_atv", {
							payload: JSON.stringify({ name: botao.dataset.atv }),
						}),
					"Acordo apagado."
				);
				break;
			case "apagar-funcao":
				mostrarConfirmacaoDeExclusao(true);
				break;
			case "apagar-funcao-cancelar":
				mostrarConfirmacaoDeExclusao(false);
				break;
			case "apagar-funcao-confirmar":
				executar(
					botao,
					() => chamar("gris.api.gestao_adultos.apagar_funcao", payloadDaLinha()),
					"Função apagada."
				).then((resultado) => {
					if (resultado) dlg.close();
				});
				break;
			default:
				break;
		}
	}

	// `salvar_atv` substitui o registro inteiro, então virar o switch precisa reenviar as
	// datas. Elas vêm da lista carregada, não do DOM.
	function alternarAssinatura(switchDaLinha) {
		const atv = atvsAtuais.find((item) => item.name === switchDaLinha.dataset.atv);
		if (!atv) {
			return;
		}
		const assinado = switchDaLinha.checked;
		executar(
			switchDaLinha,
			() =>
				chamar(
					"gris.api.gestao_adultos.salvar_atv",
					payloadDaLinha({
						name: atv.name,
						data_inicio: atv.data_inicio,
						data_fim: atv.data_fim,
						assinado: assinado ? 1 : 0,
					})
				),
			assinado ? "Acordo marcado como assinado." : "Acordo marcado como não assinado."
		).then((resultado) => {
			// Recusa do servidor: o switch já virou na tela e precisa voltar.
			if (!resultado) switchDaLinha.checked = !assinado;
		});
	}

	function escapeHtml(valor) {
		const div = document.createElement("div");
		div.textContent = valor == null ? "" : String(valor);
		return div.innerHTML;
	}

	function textoSimples(html) {
		return (
			new DOMParser().parseFromString(String(html || ""), "text/html").body.textContent || ""
		);
	}

	// -- Ligação ------------------------------------------------------------

	document.addEventListener("click", (evento) => {
		const fechar = evento.target.closest(`[data-dialog-cancel="${ID}"]`);
		if (fechar) {
			dialogo()?.close();
			return;
		}
		tratarClique(evento);
	});

	// O switch da tabela é ouvido em `change`: o rótulo repassa o clique para o input e
	// um handler de `click` rodaria duas vezes por toque.
	document.addEventListener("change", (evento) => {
		const alvo = evento.target;
		if (!alvo.matches || !alvo.matches('[data-acao="alternar-assinatura"]')) return;
		const dlg = dialogo();
		if (!dlg || !linhaAtual || !dlg.contains(alvo)) return;
		alternarAssinatura(alvo);
	});

	window.grisFuncaoOrganograma = {
		abrir(linha, opcoes) {
			const dlg = dialogo();
			if (!dlg || !linha) return;
			aoMudar = (opcoes || {}).aoMudar || null;
			aoMudarValidade = (opcoes || {}).aoMudarValidade || null;
			preencher(linha);
			dlg.showModal();
			if (linha.comAtv !== false && !linha.automatica) carregarAtvs();
		},
	};
})();
