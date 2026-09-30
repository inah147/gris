/*
 * Apoio comum às páginas de /captacao: transporte, escape, toast e formatação.
 *
 * Carregado por templates/includes/captacao_comum.html, sem `defer`, para estar
 * pronto quando o script co-localizado de cada página (injetado inline no fim do
 * body) rodar. Expõe `window.grisCaptacao`.
 */
(function () {
	"use strict";

	const API = "gris.api.captacao.endpoints.";

	const ROTULO_DE_STATUS = {
		Preliminar: "badge-outline",
		"Aprovado inicialmente": "badge-secondary",
		"Em detalhamento": "badge-secondary",
		"Revisão técnica": "badge-secondary",
		"Aprovação final": "badge-secondary",
		"Pronto para captação": "badge",
		"Captação em andamento": "badge",
		"Captação finalizada": "badge",
		Cancelado: "badge-destructive",
	};

	function escapeHtml(valor) {
		const div = document.createElement("div");
		div.textContent = valor == null ? "" : String(valor);
		return div.innerHTML;
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
	 * Chama um endpoint de `gris.api.captacao.endpoints`.
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

	function dataBR(valor) {
		const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(valor || ""));
		return match ? `${match[3]}/${match[2]}/${match[1]}` : "";
	}

	function dataHoraBR(valor) {
		const match = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(String(valor || ""));
		return match
			? `${match[3]}/${match[2]}/${match[1]} ${match[4]}:${match[5]}`
			: dataBR(valor);
	}

	function aplicarMascaraData(input) {
		let valor = input.value.replace(/\D/g, "").slice(0, 8);
		if (valor.length > 4) valor = valor.replace(/^(\d{2})(\d{2})(\d{1,4}).*/, "$1/$2/$3");
		else if (valor.length > 2) valor = valor.replace(/^(\d{2})(\d{1,2}).*/, "$1/$2");
		input.value = valor;
	}

	const formatoMoeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
	function moeda(valor) {
		return formatoMoeda.format(Number(valor) || 0);
	}

	function badgeDeStatus(status) {
		return `<span class="${ROTULO_DE_STATUS[status] || "badge-outline"}">${escapeHtml(
			status
		)}</span>`;
	}

	/** Parágrafos a partir de texto puro, preservando as quebras de linha. */
	function paragrafos(texto) {
		const limpo = String(texto || "").trim();
		if (!limpo) return '<p class="captacao-vazio">Não preenchido.</p>';
		return limpo
			.split(/\n{2,}/)
			.map((bloco) => `<p>${escapeHtml(bloco).replace(/\n/g, "<br>")}</p>`)
			.join("");
	}

	/** Quem propôs o projeto: o mesmo bloco da página do projeto e do detalhamento. */
	function blocoDoProponente(projeto) {
		const proponente = (projeto && projeto.proponente) || {};
		const tipo = proponente.tipo_rotulo
			? ` <span class="badge-outline">${escapeHtml(proponente.tipo_rotulo)}</span>`
			: "";
		const enviado =
			projeto && projeto.criado_em
				? ` · enviou a ideia em ${dataBR(projeto.criado_em)}`
				: "";
		return `<article class="card captacao-bloco" id="secao-proponente">
			<section class="captacao-bloco__corpo">
				<div class="captacao-proponente" aria-label="Proponente">
					<span class="captacao-proponente__icone" aria-hidden="true">${icone("user")}</span>
					<div class="captacao-proponente__texto">
						<p class="m-0 text-sm text-muted-foreground">Proponente</p>
						<p class="m-0 font-medium">${escapeHtml(proponente.nome || "—")}${tipo}</p>
						<p class="m-0 text-sm text-muted-foreground">Quem propôs o projeto${escapeHtml(enviado)}.</p>
					</div>
				</div>
			</section>
		</article>`;
	}

	function lerJson(texto, padrao) {
		try {
			return JSON.parse(texto || "");
		} catch (e) {
			return padrao;
		}
	}

	// ───────────────────────── Gantt do cronograma ─────────────────────────
	//
	// O cronograma conta dias do projeto (dia 0, dia 10, dia 54…), e não datas: o
	// projeto só começa quando um edital o financia. O intervalo é contínuo — do dia 0
	// ao dia 10 são 10 dias, e a atividade seguinte pode começar no dia 10.

	// Passos da régua, em dias: vale o menor que ainda deixa os rótulos caberem.
	const PASSOS_DA_REGUA = [1, 2, 5, 10, 15, 30, 60, 90, 180, 365];

	function _inteiro(valor) {
		const texto = String(valor ?? "").trim();
		if (!/^\d+$/.test(texto)) return null;
		return Number(texto);
	}

	function _dias(n) {
		return n === 1 ? "1 dia" : `${n} dias`;
	}

	function periodoDaAtividade(inicio, termino) {
		return `Dia ${inicio} ao dia ${termino} · ${_dias(termino - inicio)}`;
	}

	/**
	 * Gantt das atividades de um projeto, em dias do projeto.
	 *
	 * `desenhar(atividades)` recebe `[{indice, atividade, dia_inicio, dia_termino}]`; o
	 * que não tem título ou tem duração zero (dias não preenchidos) fica de fora. Com
	 * `opcoes.editavel`, arrastar a barra desloca a atividade e as pontas mudam início e
	 * término (mouse, toque ou setas do teclado); `opcoes.aoMudarDias(indice, inicio,
	 * termino)` recebe os dias novos.
	 */
	function criarGantt(container, opcoes) {
		const config = opcoes || {};
		let atividades = [];
		let escala = null;
		let arraste = null;

		function desenhar(lista) {
			atividades = lista || atividades;
			const itens = atividades
				.map((item) => {
					const inicio = _inteiro(item.dia_inicio);
					const termino = _inteiro(item.dia_termino);
					const titulo = String(item.atividade || "").trim();
					if (!titulo || inicio === null || termino === null || termino <= inicio)
						return null;
					return { ...item, titulo, inicio, termino };
				})
				.filter(Boolean);

			if (!itens.length) {
				escala = null;
				container.innerHTML = `<div class="captacao-gantt__vazio">${
					config.editavel
						? "Preencha a atividade e os dias de início e de término para ver o cronograma."
						: "Nenhuma atividade com período definido."
				}</div>`;
				return;
			}

			// Uma folga à direita deixa arrastar a última atividade para mais longe.
			const ultimoDia = Math.max(...itens.map((i) => i.termino));
			const totalDias = ultimoDia + Math.max(1, Math.ceil(ultimoDia * 0.05));
			escala = { totalDias };

			const pct = (dias) => `${((dias / totalDias) * 100).toFixed(4)}%`;
			// A largura da faixa (e não do container): é nela que as marcas caem. No
			// celular o nome vai acima da faixa, que ocupa a largura toda.
			const empilhado = Boolean(
				window.matchMedia && window.matchMedia("(max-width: 640px)").matches
			);
			const largura = Math.max((container.clientWidth || 600) - (empilhado ? 0 : 220), 200);
			const cabem = Math.max(2, Math.floor(largura / 56));
			const passo = PASSOS_DA_REGUA.find((p) => totalDias / p <= cabem) || 365;
			const marcas = [];
			for (let dia = 0; dia < totalDias; dia += passo) {
				marcas.push(
					`<span class="captacao-gantt__marca" style="left:${pct(
						dia
					)}"><span>dia ${dia}</span></span>`
				);
			}
			const editavel = Boolean(config.editavel);

			container.innerHTML = `<div class="captacao-gantt${
				editavel ? " captacao-gantt--editavel" : ""
			}">
				<div class="captacao-gantt__cabecalho">
					<div class="captacao-gantt__coluna">Atividade</div>
					<div class="captacao-gantt__regua">${marcas.join("")}</div>
				</div>
				<div class="captacao-gantt__linhas">${itens
					.map((item) => {
						const periodo = periodoDaAtividade(item.inicio, item.termino);
						const alcas = editavel
							? `<span class="captacao-gantt__alca captacao-gantt__alca--inicio" data-modo="inicio" aria-hidden="true"></span>
								<span class="captacao-gantt__alca captacao-gantt__alca--fim" data-modo="fim" aria-hidden="true"></span>`
							: "";
						return `<div class="captacao-gantt__linha">
							<div class="captacao-gantt__rotulo" title="${escapeHtml(item.titulo)}">
								<span class="captacao-gantt__titulo">${escapeHtml(item.titulo)}</span>
								<span class="captacao-gantt__periodo" data-periodo>${escapeHtml(periodo)}</span>
							</div>
							<div class="captacao-gantt__faixa">
								<div class="captacao-gantt__barra" data-indice="${escapeHtml(item.indice)}"
									data-inicio="${item.inicio}" data-termino="${item.termino}"
									style="left:${pct(item.inicio)};width:${pct(item.termino - item.inicio)}"
									title="${escapeHtml(`${item.titulo}: ${periodo}`)}"
									${
										editavel
											? `tabindex="0" aria-label="${escapeHtml(
													`${item.titulo}, ${periodo}. Setas movem; Shift com setas muda o término.`
											  )}"`
											: ""
									}>
									${alcas}
									<span class="captacao-gantt__barra-texto">${escapeHtml(item.titulo)}</span>
								</div>
							</div>
						</div>`;
					})
					.join("")}</div>
			</div>`;
		}

		function _posicionar(barra, inicio, termino) {
			const pct = (dias) => `${((dias / escala.totalDias) * 100).toFixed(4)}%`;
			barra.style.left = pct(inicio);
			barra.style.width = pct(termino - inicio);
			const periodo = barra
				.closest(".captacao-gantt__linha")
				?.querySelector("[data-periodo]");
			if (periodo) periodo.textContent = periodoDaAtividade(inicio, termino);
		}

		function _confirmar(barra, inicio, termino) {
			if (
				inicio === Number(barra.dataset.inicio) &&
				termino === Number(barra.dataset.termino)
			)
				return;
			if (typeof config.aoMudarDias === "function") {
				config.aoMudarDias(barra.dataset.indice, inicio, termino);
			}
		}

		/** Desloca sem sair do dia 0 e sem zerar a duração. */
		function _deslocar(modo, inicio0, termino0, dias) {
			if (modo === "inicio") {
				return {
					inicio: Math.min(Math.max(inicio0 + dias, 0), termino0 - 1),
					termino: termino0,
				};
			}
			if (modo === "fim") {
				return { inicio: inicio0, termino: Math.max(termino0 + dias, inicio0 + 1) };
			}
			const passo = Math.max(dias, -inicio0);
			return { inicio: inicio0 + passo, termino: termino0 + passo };
		}

		if (config.editavel) {
			container.addEventListener("pointerdown", (evento) => {
				const barra = evento.target.closest(".captacao-gantt__barra");
				if (!barra || !escala) return;
				const largura = barra.parentElement.getBoundingClientRect().width;
				if (!largura) return;
				arraste = {
					barra,
					modo: evento.target.dataset.modo || "mover",
					x0: evento.clientX,
					pxPorDia: largura / escala.totalDias,
					inicio0: Number(barra.dataset.inicio),
					termino0: Number(barra.dataset.termino),
				};
				arraste.inicio = arraste.inicio0;
				arraste.termino = arraste.termino0;
				barra.setPointerCapture(evento.pointerId);
				barra.classList.add("is-arrastando");
				evento.preventDefault();
			});

			container.addEventListener("pointermove", (evento) => {
				if (!arraste) return;
				const dias = Math.round((evento.clientX - arraste.x0) / arraste.pxPorDia);
				const { inicio, termino } = _deslocar(
					arraste.modo,
					arraste.inicio0,
					arraste.termino0,
					dias
				);
				arraste.inicio = inicio;
				arraste.termino = termino;
				_posicionar(arraste.barra, inicio, termino);
			});

			const soltar = () => {
				if (!arraste) return;
				const { barra, inicio, termino } = arraste;
				arraste = null;
				barra.classList.remove("is-arrastando");
				_confirmar(barra, inicio, termino);
			};
			container.addEventListener("pointerup", soltar);
			container.addEventListener("pointercancel", soltar);

			container.addEventListener("keydown", (evento) => {
				const barra = evento.target.closest(".captacao-gantt__barra");
				if (!barra || !["ArrowLeft", "ArrowRight"].includes(evento.key)) return;
				evento.preventDefault();
				const { inicio, termino } = _deslocar(
					evento.shiftKey ? "fim" : "mover",
					Number(barra.dataset.inicio),
					Number(barra.dataset.termino),
					evento.key === "ArrowLeft" ? -1 : 1
				);
				_confirmar(barra, inicio, termino);
			});
		}

		// A régua depende da largura: redesenha quando o espaço muda (girar o celular,
		// abrir a barra lateral).
		let larguraAnterior = 0;
		const observador =
			typeof ResizeObserver === "function"
				? new ResizeObserver(() => {
						const largura = container.clientWidth;
						if (arraste || Math.abs(largura - larguraAnterior) < 24) return;
						larguraAnterior = largura;
						desenhar();
				  })
				: null;
		if (observador) observador.observe(container);

		return {
			desenhar,
			destruir: () => observador && observador.disconnect(),
		};
	}

	document.addEventListener("input", function (evento) {
		if (evento.target.matches && evento.target.matches("[data-mascara-data]")) {
			aplicarMascaraData(evento.target);
		}
	});

	document.addEventListener("click", function (evento) {
		const cancelar = evento.target.closest("[data-dialog-cancel]");
		if (cancelar) document.getElementById(cancelar.dataset.dialogCancel)?.close();
	});

	window.grisCaptacao = {
		chamar,
		blocoDoProponente,
		criarGantt,
		periodoDaAtividade,
		escapeHtml,
		icone,
		toast,
		dataBR,
		dataHoraBR,
		moeda,
		badgeDeStatus,
		paragrafos,
		lerJson,
	};
})();
