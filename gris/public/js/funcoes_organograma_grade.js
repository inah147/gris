/* Grade "Funções no organograma": tabela das alocações da pessoa mais o formulário
 * de nova função.
 *
 * Mora em `public/` porque as duas fichas do organograma usam a mesma grade: a do
 * associado (/associados/detalhe) e a do responsável (/associados/responsavel).
 * Duplicar deixaria duas cópias para manter em sincronia — foi o mesmo motivo que
 * trouxe o dialog para cá.
 *
 * A página monta o `<table>` e chama por marcação, não por função:
 *     <div class="funcoes-organograma"
 *          data-pessoa="associado:<id>"   (ou "responsavel:<id>")
 *          data-nome="..."
 *          data-atv="0"                   (opcional: esconde a coluna de ATV)
 *          data-areas="[...]" data-linhas="[...]">
 *
 * `data-associado` continua aceito no lugar de `data-pessoa`.
 */
(function () {
	document.addEventListener("DOMContentLoaded", function () {
		const raiz = document.querySelector(".funcoes-organograma");
		if (!raiz) return;

		// Os dois tipos de pessoa do organograma têm `name` no mesmo formato (md5 de CPF),
		// então é o prefixo que diz em qual grade gravar.
		const pessoa =
			raiz.dataset.pessoa ||
			(raiz.dataset.associado ? `associado:${raiz.dataset.associado}` : "");
		const nomeDaPessoa = raiz.dataset.nome || "";
		// Acordo de trabalho voluntário é documento do quadro: a ficha do responsável
		// desliga a coluna em vez de mostrar uma pendência que ninguém pode resolver.
		const mostraAtv = raiz.dataset.atv !== "0";
		const colunas = mostraAtv ? 5 : 4;
		const corpo = document.getElementById("funcoes-organograma-corpo");
		const botaoAdicionar = document.getElementById("btn-adicionar-funcao");

		// A tabela é a fonte de qual linha o dialog abre: guardar o último render evita
		// reler o DOM para remontar o objeto da linha.
		let linhasAtuais = [];
		let areas = [];
		try {
			areas = JSON.parse(raiz.dataset.areas || "[]");
		} catch (e) {
			areas = [];
		}

		function toast(categoria, titulo) {
			document.dispatchEvent(
				new CustomEvent("basecoat:toast", {
					detail: { config: { category: categoria, title: titulo, duration: 4000 } },
				})
			);
		}

		function escapeHtml(valor) {
			const div = document.createElement("div");
			div.textContent = valor == null ? "" : String(valor);
			return div.innerHTML;
		}

		/** Texto puro da mensagem que o servidor devolve em HTML.
		 *
		 * Pelo DOM, e não por regex: tirar `<...>` numa passada só pode reconstituir a
		 * sequência perigosa (`<<script>script>` vira `<script>`). E o título do toast
		 * é inserido com `innerHTML`, então aqui não pode sobrar marcação nenhuma.
		 * `DOMParser` com "text/html" não executa script.
		 */
		function textoSimples(html) {
			const doc = new DOMParser().parseFromString(
				String(html == null ? "" : html),
				"text/html"
			);
			return (doc.body.textContent || "").trim();
		}

		function valorDoSelect(id) {
			const elemento = document.getElementById(id);
			if (!elemento) return "";
			const hidden = elemento.querySelector('input[type="hidden"]');
			return hidden ? hidden.value : "";
		}

		// Troca as opções do listbox e força o Basecoat a reinicializar o componente:
		// sem o clone, o select continua respondendo com a lista antiga.
		//
		// A primeira opção é sempre um placeholder de valor vazio, e não é decoração:
		// ao inicializar, o select seleciona sozinho a primeira opção — e em silêncio,
		// sem disparar `change`. Sem a opção vazia, a área sairia escolhida sem
		// ninguém ter escolhido, e clicar nela depois não dispararia evento nenhum
		// (o componente ignora o clique quando o valor não muda), então a cascata
		// nunca rodaria.
		function repopularSelect(id, itens, placeholder) {
			const antigo = document.getElementById(id);
			if (!antigo) return;
			const listbox = antigo.querySelector('[role="listbox"]');
			const hidden = antigo.querySelector('input[type="hidden"]');
			const rotulo = antigo.querySelector(":scope > button > span");
			if (!listbox || !hidden || !rotulo) return;

			const textoPlaceholder = placeholder == null ? "Selecione…" : placeholder;
			antigo.dataset.placeholder = textoPlaceholder;

			listbox.innerHTML = "";
			[{ value: "", label: textoPlaceholder }, ...(itens || [])].forEach((item, indice) => {
				const opcao = document.createElement("div");
				opcao.id = `${id}-items-${indice + 1}`;
				opcao.setAttribute("role", "option");
				opcao.dataset.value = item.value;
				opcao.textContent = item.label;
				listbox.appendChild(opcao);
			});

			hidden.value = "";
			rotulo.textContent = textoPlaceholder;

			const novo = antigo.cloneNode(true);
			novo.removeAttribute("data-select-initialized");
			antigo.parentNode.replaceChild(novo, antigo);
		}

		function periodoDaLinha(linha) {
			const inicio = linha.data_inicio ? frappe.datetime.str_to_user(linha.data_inicio) : "";
			if (!linha.data_fim) return inicio ? `Desde ${inicio}` : "Atual";
			const fim = frappe.datetime.str_to_user(linha.data_fim);
			return inicio ? `${inicio} – ${fim}` : `Até ${fim}`;
		}

		// Selo do Acordo de Trabalho Voluntário da linha. Vencido e não assinado são
		// pendências independentes — as duas precisam aparecer.
		function atvDaLinha(atv, atual) {
			if (!atv) return "—";
			// Função que já acabou não tem acordo a cobrar.
			if (!atual) {
				return atv.situacao === "sem_atv"
					? "—"
					: `<span class="badge-outline">Até ${escapeHtml(
							frappe.datetime.str_to_user(atv.data_fim)
					  )}</span>`;
			}
			if (atv.situacao === "sem_atv") {
				return '<span class="badge-destructive">Sem ATV</span>';
			}
			const validade =
				atv.situacao === "vencido"
					? `<span class="badge-destructive">Vencido em ${escapeHtml(
							frappe.datetime.str_to_user(atv.data_fim)
					  )}</span>`
					: `<span class="badge-outline">Até ${escapeHtml(
							frappe.datetime.str_to_user(atv.data_fim)
					  )}</span>`;
			const assinatura = atv.assinado
				? ""
				: ' <span class="badge-destructive">Não assinado</span>';
			return validade + assinatura;
		}

		function renderizar(linhas) {
			if (!corpo) return;
			linhasAtuais = linhas;
			if (!linhas.length) {
				corpo.innerHTML = `<tr><td colspan="${colunas}" class="text-muted-foreground text-sm">Nenhuma função atribuída.</td></tr>`;
				return;
			}

			corpo.innerHTML = linhas
				.map((linha) => {
					// A linha só é apagada visualmente quando de fato acabou: `data_fim`
					// no futuro é função em vigor com término já programado, e o período
					// da coluna ao lado já diz até quando.
					const principal = linha.principal
						? '<span class="badge">Principal</span>'
						: "";
					return `<tr${linha.atual ? "" : ' class="funcoes-organograma__encerrada"'}>
						<td>${escapeHtml(linha.area || "—")}</td>
						<td>${escapeHtml(linha.funcao)} ${principal}</td>
						<td>${escapeHtml(periodoDaLinha(linha))}</td>
						${mostraAtv ? `<td>${atvDaLinha(linha.atv, linha.atual)}</td>` : ""}
						<td class="funcoes-organograma__acoes">
							<button type="button" class="btn-sm-ghost" data-acao="detalhes"
								data-linha="${escapeHtml(linha.linha)}"
								aria-label="Detalhes de ${escapeHtml(linha.funcao)}">
								<svg class="ds-lucide ds-lucide--sm" aria-hidden="true" focusable="false" viewBox="0 0 24 24">
									<use href="/assets/gris/design_system/icons/lucide/sprite.svg#ellipsis" />
								</svg>
							</button>
						</td>
					</tr>`;
				})
				.join("");
		}

		// `frappe.call` no portal não chama `error` e dispara `always` antes do
		// `callback`: a mensagem do `frappe.throw` se perderia, e é ela que explica
		// por que o par função+área foi recusado.
		async function chamar(metodo, argumentos) {
			const resposta = await fetch(`/api/method/${metodo}`, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					Accept: "application/json",
					"X-Frappe-CSRF-Token": frappe.csrf_token || "",
				},
				credentials: "same-origin",
				body: JSON.stringify(argumentos),
			});

			const corpoJson = await resposta.json().catch(() => ({}));
			if (!resposta.ok) {
				let mensagem = "Não foi possível salvar.";
				try {
					const lista = JSON.parse(corpoJson._server_messages || "[]");
					if (lista.length) mensagem = JSON.parse(lista[0]).message;
				} catch (e) {
					/* fica a mensagem genérica */
				}
				throw new Error(mensagem);
			}
			return corpoJson.message;
		}

		async function executar(botao, metodo, argumentos, sucesso) {
			botao.disabled = true;
			try {
				const resultado = await chamar(metodo, argumentos);
				renderizar((resultado && resultado.funcoes) || []);
				toast("success", sucesso);
			} catch (erro) {
				// A mensagem vem do servidor e é o que explica o bloqueio.
				toast("error", textoSimples(erro.message || erro));
			} finally {
				botao.disabled = false;
			}
		}

		// A área escolhida define quais funções existem.
		function sincronizarFuncoes() {
			const escolhida = areas.find((a) => a.value === valorDoSelect("funcao-area"));
			if (!escolhida) {
				repopularSelect("funcao-funcao", [], "Escolha a área primeiro");
				return;
			}
			repopularSelect(
				"funcao-funcao",
				escolhida.funcoes,
				escolhida.funcoes.length ? "Selecione a função…" : "Nenhuma função nesta área"
			);
		}

		document.addEventListener("change", function (evento) {
			if (!evento.target.closest || !evento.target.closest("#funcao-area")) return;
			sincronizarFuncoes();
		});

		if (botaoAdicionar) {
			botaoAdicionar.addEventListener("click", function () {
				const area = valorDoSelect("funcao-area");
				const funcao = valorDoSelect("funcao-funcao");
				if (!area || !funcao) {
					toast("error", "Escolha a área e a função.");
					return;
				}
				executar(
					botaoAdicionar,
					"gris.api.gestao_adultos.atribuir_funcao",
					{
						payload: JSON.stringify({
							pessoa: pessoa,
							area: area,
							funcao: funcao,
						}),
					},
					"Função atribuída."
					// Recarrega as funções da mesma área em vez de só limpar: re-clicar a
					// área já escolhida não dispara `change`, então limpar deixaria o
					// seletor vazio e sem jeito de voltar a preencher.
				).then(sincronizarFuncoes);
			});
		}

		// Encerrar, tornar principal, corrigir datas, apagar e cuidar dos ATVs vivem
		// todos no dialog compartilhado com /gestao_adultos/atvs.
		raiz.addEventListener("click", function (evento) {
			const botao = evento.target.closest('[data-acao="detalhes"]');
			if (!botao || !window.grisFuncaoOrganograma) return;

			const linha = linhasAtuais.find((item) => item.linha === botao.dataset.linha);
			if (!linha) return;

			window.grisFuncaoOrganograma.abrir(
				Object.assign({ pessoa: pessoa, nome: nomeDaPessoa, comAtv: mostraAtv }, linha),
				{ aoMudar: renderizar }
			);
		});

		repopularSelect(
			"funcao-area",
			areas.map((a) => ({ value: a.value, label: a.label })),
			"Selecione a área…"
		);
		renderizar(JSON.parse(raiz.dataset.linhas || "[]"));
	});
})();
