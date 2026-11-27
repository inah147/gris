/*
 * Apoio comum às páginas de /administracao/assembleias e /assembleias: transporte,
 * escape, toast, datas e o calendário do datepicker dentro de <dialog>.
 *
 * Carregado por templates/includes/assembleias_comum.html, sem `defer`, para estar
 * pronto quando o script co-localizado de cada página (injetado inline no fim do
 * body) rodar. Expõe `window.grisAssembleias`.
 */
(function () {
	"use strict";

	const API = "gris.api.assembleias.";
	const DISTANCIA_DO_CAMPO = 6;
	const MARGEM_DA_TELA = 8;

	function escapeHtml(valor) {
		// Por substituição, e não pelo truque textContent -> innerHTML: aquele não escapa
		// aspas, e o texto também vai para atributos (title, aria-label, href).
		return String(valor == null ? "" : valor)
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;")
			.replace(/'/g, "&#39;");
	}

	function icone(nome, tamanho) {
		return `<svg class="ds-lucide ds-lucide--${
			tamanho || "sm"
		}" aria-hidden="true" focusable="false" viewBox="0 0 24 24"><use href="/assets/gris/design_system/icons/lucide/sprite.svg#${nome}" /></svg>`;
	}

	/** Texto puro da mensagem do servidor. Pelo DOM, e não por regex: tirar `<...>`
	 * numa passada só pode reconstituir marcação. `DOMParser` não executa script. */
	function textoSimples(html) {
		const doc = new DOMParser().parseFromString(String(html == null ? "" : html), "text/html");
		return (doc.body.textContent || "").trim();
	}

	function toast(categoria, titulo) {
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: { config: { category: categoria, title: titulo, duration: 4500 } },
			})
		);
	}

	/**
	 * Chama `gris.api.assembleias.<metodo>`.
	 *
	 * `fetch`, e não `frappe.call`: no portal, `frappe.call` nunca chama o `error` e
	 * engole a mensagem do `frappe.throw`, que é o que explica a recusa.
	 */
	async function chamar(metodo, args) {
		const resposta = await fetch(`/api/method/${API}${metodo}`, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				Accept: "application/json",
				"X-Frappe-CSRF-Token": (window.frappe && frappe.csrf_token) || "",
			},
			credentials: "same-origin",
			body: JSON.stringify(args || {}),
		});
		const json = await resposta.json().catch(() => ({}));
		if (!resposta.ok) {
			let mensagem = "Não foi possível concluir a ação.";
			try {
				const lista = JSON.parse(json._server_messages || "[]");
				if (lista.length) mensagem = JSON.parse(lista[lista.length - 1]).message;
			} catch (e) {
				/* fica a mensagem genérica */
			}
			throw new Error(textoSimples(mensagem));
		}
		return json.message;
	}

	/**
	 * Baixa um PDF de `gris.api.assembleias.<metodo>`. Por POST e `fetch`, e não por
	 * `window.open`: um erro do servidor vira toast em vez de uma aba com traceback.
	 */
	async function baixarPdf(metodo, args, nomeDoArquivo) {
		const resposta = await fetch(`/api/method/${API}${metodo}`, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				"X-Frappe-CSRF-Token": (window.frappe && frappe.csrf_token) || "",
			},
			credentials: "same-origin",
			body: JSON.stringify(args || {}),
		});
		const tipo = resposta.headers.get("Content-Type") || "";
		if (!resposta.ok || !tipo.includes("pdf")) {
			const json = await resposta.json().catch(() => ({}));
			let mensagem = "Não foi possível gerar o PDF.";
			try {
				const lista = JSON.parse(json._server_messages || "[]");
				if (lista.length) mensagem = JSON.parse(lista[lista.length - 1]).message;
			} catch (e) {
				/* fica a mensagem genérica */
			}
			throw new Error(textoSimples(mensagem));
		}
		const url = URL.createObjectURL(await resposta.blob());
		const link = document.createElement("a");
		link.href = url;
		link.download = nomeDoArquivo;
		document.body.appendChild(link);
		link.click();
		link.remove();
		setTimeout(() => URL.revokeObjectURL(url), 10000);
	}

	function lerJson(texto, padrao) {
		try {
			return JSON.parse(texto || "");
		} catch (e) {
			return padrao;
		}
	}

	function dataBR(valor) {
		const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(valor || ""));
		return match ? `${match[3]}/${match[2]}/${match[1]}` : "";
	}

	const DIAS_DA_SEMANA = ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"];

	function diaDaSemana(valor) {
		const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(valor || ""));
		if (!match) return "";
		return DIAS_DA_SEMANA[new Date(+match[1], +match[2] - 1, +match[3]).getDay()];
	}

	/** O select do design system expõe `value` na raiz; o hidden guarda o valor atual. */
	function valorDoSelect(id) {
		const elemento = document.getElementById(id);
		if (!elemento) return "";
		const hidden = elemento.querySelector('input[type="hidden"]');
		return hidden ? hidden.value : "";
	}

	function definirComponente(id, valor) {
		const elemento = document.getElementById(id);
		if (elemento) elemento.value = valor == null ? "" : String(valor);
	}

	/** O switch do design system põe o id no rótulo, não no checkbox. */
	function switchDe(id) {
		const rotulo = document.getElementById(id);
		return rotulo ? rotulo.querySelector('input[type="checkbox"]') : null;
	}

	function posicionarCalendario(raizData, calendario) {
		const campo = raizData.querySelector(".datepicker-trigger").getBoundingClientRect();
		const altura = calendario.offsetHeight;
		const largura = calendario.offsetWidth;
		let topo = campo.bottom + DISTANCIA_DO_CAMPO;
		if (topo + altura > window.innerHeight - MARGEM_DA_TELA) {
			const acima = campo.top - DISTANCIA_DO_CAMPO - altura;
			topo =
				acima >= MARGEM_DA_TELA
					? acima
					: Math.max(MARGEM_DA_TELA, window.innerHeight - MARGEM_DA_TELA - altura);
		}
		const esquerda = Math.max(
			MARGEM_DA_TELA,
			Math.min(campo.left, window.innerWidth - MARGEM_DA_TELA - largura)
		);
		calendario.style.top = `${Math.round(topo)}px`;
		calendario.style.left = `${Math.round(esquerda)}px`;
	}

	/**
	 * Põe o calendário dos datepickers de um <dialog> na top layer (Popover API), acima do
	 * próprio dialog: dentro dele o calendário é recortado ou estica a caixa.
	 */
	function calendariosPorCimaDoDialog(dialog) {
		if (!dialog) return;
		dialog.querySelectorAll("[data-datepicker]").forEach((raizData) => {
			const calendario = raizData.querySelector(".datepicker-popover");
			if (!calendario || typeof calendario.showPopover !== "function") return;
			calendario.setAttribute("popover", "manual");
			const aberto = () => calendario.matches(":popover-open");
			new MutationObserver(() => {
				if (calendario.hidden) {
					if (aberto()) calendario.hidePopover();
				} else if (!aberto()) {
					calendario.showPopover();
					posicionarCalendario(raizData, calendario);
				}
			}).observe(calendario, { attributes: true, attributeFilter: ["hidden"] });
			const reposicionar = () => aberto() && posicionarCalendario(raizData, calendario);
			new ResizeObserver(reposicionar).observe(calendario);
			dialog.addEventListener("scroll", reposicionar, true);
			window.addEventListener("resize", reposicionar);
		});
		dialog.addEventListener("close", () => {
			dialog.querySelectorAll("[data-datepicker]").forEach((raizData) => {
				if (typeof raizData.close === "function") raizData.close();
			});
		});
	}

	/** Valor ISO (AAAA-MM-DD) de um datepicker, pelo hidden do componente. */
	function valorDaData(id) {
		const raiz = document.getElementById(id);
		const hidden = raiz && raiz.querySelector('input[type="hidden"]');
		return hidden ? hidden.value : "";
	}

	// ───────────────────────── Componentes gerados no JS ─────────────────────────

	let sequencia = 0;
	function novoId(prefixo) {
		sequencia += 1;
		return `${prefixo}-${Date.now().toString(36)}-${sequencia}`;
	}

	/**
	 * O mesmo markup da macro `select` do design system, para listas montadas no JS. O
	 * observer do Basecoat inicializa o componente quando ele entra no DOM. A opção
	 * escolhida já sai marcada no HTML, então não é preciso escrever `.value` depois.
	 */
	function selectHtml(id, itens, selecionado, atributos) {
		const atual = itens.find((item) => item.value === (selecionado || "")) || itens[0] || {};
		const opcoes = itens
			.map(
				(item, i) =>
					`<div id="${id}-items-${i + 1}" role="option" data-value="${escapeHtml(
						item.value
					)}"${item.value === atual.value ? ' aria-selected="true"' : ""}>${escapeHtml(
						item.label
					)}</div>`
			)
			.join("");
		return `<div id="${id}" class="select ${(atributos && atributos.class) || ""}">
			<button type="button" class="btn-outline w-full" id="${id}-trigger" aria-haspopup="listbox" aria-expanded="false" aria-controls="${id}-listbox"${
			atributos && atributos.label ? ` aria-label="${escapeHtml(atributos.label)}"` : ""
		}>
				<span class="truncate">${escapeHtml(atual.label || "")}</span>
				<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-chevron-down text-muted-foreground opacity-50 shrink-0"><path d="m6 9 6 6 6-6"/></svg>
			</button>
			<div id="${id}-popover" data-popover aria-hidden="true">
				<div role="listbox" id="${id}-listbox" aria-orientation="vertical" aria-labelledby="${id}-trigger">${opcoes}</div>
			</div>
			<input type="hidden" name="${id}-value" value="${escapeHtml(atual.value || "")}">
		</div>`;
	}

	function switchHtml(rotulo, marcado, atributos) {
		return `<label class="switch ${
			(atributos && atributos.class) || ""
		}"><input type="checkbox" role="switch" class="input"${marcado ? " checked" : ""}${
			atributos && atributos.data ? ` ${atributos.data}` : ""
		}> <span>${escapeHtml(rotulo)}</span></label>`;
	}

	/**
	 * Editor de pauta: incluir, excluir, reordenar, título, votação, finalidade e
	 * orientação. Usado nas configurações (pautas padrão) e na aba Edital.
	 *
	 * `opcoes.finalidades`: [{label, value}] com a opção vazia primeiro.
	 * `opcoes.somenteLeitura`: mostra a pauta sem controles (edital publicado).
	 * `opcoes.orientacaoPadrao(finalidade)`: texto sugerido para um item novo.
	 * `opcoes.semOrientacao`: esconde a orientação (na assembleia ela é editada na Condução).
	 * Devolve `{ itens() }`, que lê o estado atual do DOM.
	 */
	function criarEditorDePauta(container, itensIniciais, opcoes) {
		const config = opcoes || {};
		const finalidades = config.finalidades || [{ label: "Sem finalidade", value: "" }];
		const lista = document.createElement("ol");
		lista.className = "asm-pauta";
		container.innerHTML = "";
		container.appendChild(lista);

		function linhaHtml(item) {
			const id = novoId("pauta-finalidade");
			if (config.somenteLeitura) {
				return `<li class="asm-pauta__item asm-pauta__item--leitura" data-item>
					<div class="asm-pauta__linha">
						<span class="asm-pauta__numero" data-numero></span>
						<p class="m-0">${escapeHtml(item.titulo)}${
					item.tem_votacao ? ' <span class="badge-outline">Votação</span>' : ""
				}</p>
					</div>
				</li>`;
			}
			return `<li class="asm-pauta__item" data-item data-name="${escapeHtml(
				item.name || ""
			)}">
				<div class="asm-pauta__linha">
					<span class="asm-pauta__numero" data-numero></span>
					<textarea class="textarea" rows="1" data-campo="titulo" aria-label="Título do item">${escapeHtml(
						item.titulo
					)}</textarea>
					<div class="asm-pauta__acoes">
						<button type="button" class="btn-sm-ghost" data-acao="subir" aria-label="Subir item">${icone(
							"arrow-up"
						)}</button>
						<button type="button" class="btn-sm-ghost" data-acao="descer" aria-label="Descer item">${icone(
							"arrow-down"
						)}</button>
						<button type="button" class="btn-sm-ghost" data-acao="remover" aria-label="Excluir item">${icone(
							"trash-2"
						)}</button>
					</div>
				</div>
				<div class="asm-pauta__opcoes">
					${switchHtml("Tem votação", !!item.tem_votacao, { data: 'data-campo="tem_votacao"' })}
					${selectHtml(id, finalidades, item.finalidade || "", { label: "Finalidade" })}
				</div>
				${
					config.semOrientacao
						? ""
						: `<details class="asm-pauta__orientacao">
					<summary>Orientação de condução</summary>
					<textarea class="textarea asm-textarea-alta" data-campo="orientacao_conducao" aria-label="Orientação de condução">${escapeHtml(
						item.orientacao_conducao || ""
					)}</textarea>
				</details>`
				}
			</li>`;
		}

		function renumerar() {
			lista.querySelectorAll("[data-numero]").forEach((el, i) => {
				el.textContent = `${i + 1}.`;
			});
		}

		function adicionar(item) {
			lista.insertAdjacentHTML("beforeend", linhaHtml(item));
			renumerar();
		}

		(itensIniciais || []).forEach(adicionar);

		if (!config.somenteLeitura) {
			lista.addEventListener("click", (evento) => {
				const botao = evento.target.closest("[data-acao]");
				if (!botao) return;
				const item = botao.closest("[data-item]");
				if (botao.dataset.acao === "remover") item.remove();
				if (botao.dataset.acao === "subir" && item.previousElementSibling) {
					lista.insertBefore(item, item.previousElementSibling);
				}
				if (botao.dataset.acao === "descer" && item.nextElementSibling) {
					lista.insertBefore(item.nextElementSibling, item);
				}
				renumerar();
			});
			// Escolher a finalidade num item sem orientação sugere a orientação dela.
			lista.addEventListener("change", (evento) => {
				const select = evento.target.closest(".select");
				if (!select || !config.orientacaoPadrao) return;
				const item = select.closest("[data-item]");
				const orientacao = item.querySelector('[data-campo="orientacao_conducao"]');
				if (orientacao && !orientacao.value.trim()) {
					const valor = select.querySelector('input[type="hidden"]').value;
					orientacao.value = config.orientacaoPadrao(valor) || "";
				}
			});
		}

		function itens() {
			return Array.from(lista.querySelectorAll("[data-item]")).map((li) => {
				const item = {
					name: li.dataset.name || "",
					titulo: (li.querySelector('[data-campo="titulo"]')?.value || "").trim(),
					tem_votacao: li.querySelector('[data-campo="tem_votacao"]')?.checked ? 1 : 0,
					finalidade: li.querySelector('.select input[type="hidden"]')?.value || "",
				};
				// Sem o campo na tela, a orientação não vai: o servidor mantém a gravada.
				const orientacao = li.querySelector('[data-campo="orientacao_conducao"]');
				if (orientacao) item.orientacao_conducao = orientacao.value.trim();
				return item;
			});
		}

		return {
			itens,
			adicionar: (item) =>
				adicionar(
					item || { titulo: "", tem_votacao: 0, finalidade: "", orientacao_conducao: "" }
				),
		};
	}

	// ───────────────────────── Salvamento automático ─────────────────────────

	function mesclar(destino, origem) {
		Object.keys(origem).forEach((chave) => {
			const valor = origem[chave];
			if (valor && typeof valor === "object" && !Array.isArray(valor)) {
				destino[chave] = mesclar(destino[chave] || {}, valor);
			} else {
				destino[chave] = valor;
			}
		});
		return destino;
	}

	/**
	 * Fila de salvamento automático de uma assembleia (CA-08.2, CA-08.3).
	 *
	 * `agendar(campos, indicador)` junta as mudanças e grava ~800 ms depois da última.
	 * Uma gravação de cada vez: o `modified` devolvido vira o da próxima, e se outra
	 * janela gravou no meio o servidor responde `conflito` e nada é sobrescrito.
	 * `opcoes.metodo` é o endpoint (`pagina.salvar_campos` ou `ata.salvar_campos`);
	 * `opcoes.aoSalvar(resposta)` recebe o retorno.
	 */
	function criarSalvamentoAutomatico(estado, opcoes) {
		let pendente = {};
		const indicadores = new Set();
		let timer = null;
		let gravando = false;
		let conflito = false;

		function indicar(texto, classe) {
			indicadores.forEach((el) => {
				el.textContent = texto;
				el.dataset.estado = classe;
			});
		}

		async function gravar() {
			timer = null;
			if (gravando || conflito || !Object.keys(pendente).length) return;
			const campos = pendente;
			pendente = {};
			gravando = true;
			indicar("Salvando…", "salvando");
			try {
				const resposta = await chamar(opcoes.metodo, {
					name: estado.name,
					campos: JSON.stringify(campos),
					modified: estado.modified,
				});
				if (resposta && resposta.conflito) {
					conflito = true;
					indicar("Alterada em outra janela — recarregue a página", "erro");
					toast(
						"error",
						"A assembleia foi alterada em outra janela. Recarregue a página para continuar."
					);
					return;
				}
				estado.modified = resposta.modified;
				indicar(`Salvo às ${resposta.salvo_em}`, "salvo");
				if (opcoes.aoSalvar) opcoes.aoSalvar(resposta);
			} catch (erro) {
				// Devolve à fila para tentar de novo na próxima mudança ou no clique.
				pendente = mesclar(campos, pendente);
				indicar("Não foi possível salvar — tentar de novo", "erro");
				toast("error", erro.message);
			} finally {
				gravando = false;
				if (Object.keys(pendente).length && !conflito) timer = setTimeout(gravar, 800);
			}
		}

		function agendar(campos, indicador) {
			if (conflito) return;
			mesclar(pendente, campos);
			if (indicador) indicadores.add(indicador);
			indicar("Alterações não salvas", "pendente");
			clearTimeout(timer);
			timer = setTimeout(gravar, 800);
		}

		// Sair com alteração pendente pede confirmação.
		window.addEventListener("beforeunload", (evento) => {
			if (Object.keys(pendente).length || gravando) {
				evento.preventDefault();
				evento.returnValue = "";
			}
		});

		// "tentar de novo": clicar no indicador de erro grava já.
		document.addEventListener("click", (evento) => {
			const el = evento.target.closest("[data-salvamento]");
			if (el && el.dataset.estado === "erro" && !conflito) {
				clearTimeout(timer);
				gravar();
			}
		});

		return { agendar, gravarAgora: gravar };
	}

	// Botões "Cancelar" dos dialogs: `data-dialog-cancel="<id do dialog>"`.
	document.addEventListener("click", function (evento) {
		const cancelar = evento.target.closest("[data-dialog-cancel]");
		if (cancelar) document.getElementById(cancelar.dataset.dialogCancel)?.close();
	});

	window.grisAssembleias = {
		escapeHtml,
		icone,
		textoSimples,
		toast,
		chamar,
		baixarPdf,
		lerJson,
		dataBR,
		diaDaSemana,
		valorDoSelect,
		definirComponente,
		switchDe,
		calendariosPorCimaDoDialog,
		valorDaData,
		selectHtml,
		switchHtml,
		criarEditorDePauta,
		criarSalvamentoAutomatico,
	};
})();
