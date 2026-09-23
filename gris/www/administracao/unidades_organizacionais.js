// Gestão das unidades organizacionais: tabela e árvore interativa.
//
// As duas visualizações leem o mesmo array `unidades`, recarregado inteiro a cada
// gravação — a estrutura da UEL tem dezenas de áreas, não milhares, e manter uma
// única fonte evita as duas telas divergirem.
(function () {
	const raiz = document.querySelector(".admin-unidades");
	if (!raiz) return;

	const PODE_EDITAR = raiz.dataset.podeEditar === "1";
	const dialogArea = document.getElementById("dialog-area");

	let unidades = lerJson(raiz.dataset.unidades);
	const opcoesFuncao = lerJson(raiz.dataset.opcoesFuncao);
	let funcoesNoDialog = [];

	// Áreas com os filhos escondidos. Mora aqui, e não no servidor: é estado de
	// leitura da tela, não do cadastro.
	const colapsados = new Set();

	function lerJson(texto) {
		try {
			return JSON.parse(texto || "[]");
		} catch (e) {
			return [];
		}
	}

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

	/** Texto puro da mensagem que o servidor devolve em HTML.
	 *
	 * Pelo DOM, e não por regex: tirar `<...>` numa passada só pode reconstituir a
	 * sequência perigosa (`<<script>script>` vira `<script>`). E o título do toast
	 * é inserido com `innerHTML`, então aqui não pode sobrar marcação nenhuma.
	 * `DOMParser` com "text/html" não executa script.
	 */
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

	function porNome(nome) {
		return unidades.find((u) => u.name === nome) || null;
	}

	// `frappe.call` no portal engole a mensagem do `frappe.throw`, e aqui ela é o
	// conteúdo: é ela que diz quantas pessoas ainda ocupam a função, ou que a
	// hierarquia ficaria circular.
	async function chamar(metodo, corpo) {
		const resposta = await fetch(`/api/method/${metodo}`, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				Accept: "application/json",
				"X-Frappe-CSRF-Token": frappe.csrf_token || "",
			},
			credentials: "same-origin",
			body: JSON.stringify({ payload: JSON.stringify(corpo) }),
		});
		const json = await resposta.json().catch(() => ({}));
		if (!resposta.ok) {
			let mensagem = "Não foi possível salvar.";
			try {
				const lista = JSON.parse(json._server_messages || "[]");
				if (lista.length) mensagem = JSON.parse(lista[0]).message;
			} catch (e) {
				/* fica a mensagem genérica */
			}
			throw new Error(textoSimples(mensagem));
		}
		return json.message;
	}

	function aplicar(resultado) {
		if (resultado && resultado.unidades) {
			unidades = resultado.unidades;
			renderizarTudo();
		}
	}

	// ------------------------------------------------------------------
	// Visualização em tabela
	// ------------------------------------------------------------------

	function cabecalhoOrdenavel(rotulo) {
		return `<th aria-sort="none" data-sortable><button type="button" class="table-sort-trigger"><span>${rotulo}</span>${icone(
			"chevrons-up-down",
			"xs"
		).replace("ds-lucide--xs", "ds-lucide--xs table-sort-icon")}</button></th>`;
	}

	function renderizarTabela() {
		const alvo = document.getElementById("admin-unidades-tabela");
		if (!alvo) return;

		const linhas = unidades
			.map((u) => {
				const acoes = PODE_EDITAR
					? `<button type="button" class="btn-sm-ghost admin-unidades__menu" data-acao="editar" data-name="${escapeHtml(
							u.name
					  )}" aria-label="Editar ${escapeHtml(u.area)}">${icone("ellipsis")}</button>`
					: "";
				const status = u.ativa
					? '<span class="badge">Ativa</span>'
					: '<span class="badge-outline">Inativa</span>';
				const automatica = u.origem_automatica
					? ` <span class="badge-outline admin-unidades__auto">automática</span>`
					: "";
				return `<tr>
					<td data-sort-value="${escapeHtml(u.area)}">${escapeHtml(u.area)}${automatica}</td>
					<td>${escapeHtml(u.responde_para || "—")}</td>
					<td>${escapeHtml(u.responsavel_nome || "—")}</td>
					<td data-sort-value="${u.ativa ? 1 : 0}">${status}</td>
					<td class="admin-unidades__acoes">${acoes}</td>
				</tr>`;
			})
			.join("");

		alvo.innerHTML = `<table class="table table-sortable admin-unidades__tabela" data-table-sortable>
			<thead>
				<tr>
					${cabecalhoOrdenavel("Área")}
					${cabecalhoOrdenavel("A quem responde")}
					${cabecalhoOrdenavel("Responsável")}
					${cabecalhoOrdenavel("Status")}
					<th class="admin-unidades__acoes"></th>
				</tr>
			</thead>
			<tbody>${linhas}</tbody>
		</table>`;
	}

	// ------------------------------------------------------------------
	// Visualização em árvore
	// ------------------------------------------------------------------

	const LARGURA = 200;
	const ALTURA = 92;
	const GAP_X = 28;
	const GAP_Y = 76;
	const ZOOM_MIN = 0.2;
	const ZOOM_MAX = 2;
	//: A bolinha do pai encosta no card, logo abaixo da borda de onde a linha sai.
	//: O centro precisa ficar fora do card: o card é desenhado por cima do SVG, e
	//: com o centro sobre a borda quem recebe o ponteiro é o card, não a alça. Com
	//: o raio da seleção (8) a bolinha ainda toca o card.
	//: O botão "+" ocupa esse mesmo lugar, e por isso é desligado no card pai
	//: enquanto a linha está selecionada.
	const FOLGA_PONTA_PAI = 7;
	const FOLGA_PONTA_FILHO = 8;

	// Pan e zoom aplicados por transform no canvas — os cards não se movem entre si,
	// só a posição do desenho na tela.
	const vista = { escala: 1, x: 0, y: 0, largura: 0, altura: 0 };

	function elArvore() {
		const painel = document.getElementById("admin-unidades-arvore");
		if (!painel) return null;
		return {
			painel: painel,
			palco: painel.querySelector(".admin-arvore__palco"),
			canvas: painel.querySelector(".admin-arvore__canvas"),
			svg: painel.querySelector(".admin-arvore__linhas"),
			cards: painel.querySelector(".admin-arvore__cards"),
			nivel: painel.querySelector(".admin-arvore__nivel"),
		};
	}

	function aplicarTransform() {
		const el = elArvore();
		if (!el || !el.canvas) return;
		el.canvas.style.transform = `translate(${vista.x}px, ${vista.y}px) scale(${vista.escala})`;
		if (el.nivel) el.nivel.textContent = `${Math.round(vista.escala * 100)}%`;
	}

	function definirEscala(nova, ancoraX, ancoraY) {
		const el = elArvore();
		if (!el || !el.palco) return;
		const limitada = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, nova));
		if (limitada === vista.escala) return;

		const caixa = el.palco.getBoundingClientRect();
		const px = ancoraX === undefined ? caixa.width / 2 : ancoraX - caixa.left;
		const py = ancoraY === undefined ? caixa.height / 2 : ancoraY - caixa.top;
		const fator = limitada / vista.escala;

		// Mantém sob o cursor o mesmo ponto do desenho depois do zoom.
		vista.x = px - (px - vista.x) * fator;
		vista.y = py - (py - vista.y) * fator;
		vista.escala = limitada;
		aplicarTransform();
	}

	function ajustarATela() {
		const el = elArvore();
		if (!el || !el.palco || !vista.largura) return;
		let caixa = el.palco.getBoundingClientRect();
		if (!caixa.width || !caixa.height) return;

		vista.escala = Math.min(
			ZOOM_MAX,
			Math.max(
				ZOOM_MIN,
				Math.min(caixa.width / vista.largura, caixa.height / vista.altura) * 0.95
			)
		);

		// Encolhe o palco quando a árvore é larga e baixa: a escala cai por causa da
		// largura e sobraria uma faixa vazia de centenas de pixels embaixo. Só o
		// ajuste mexe na altura — dar zoom depois não fica redimensionando o quadro.
		const desejada = vista.altura * vista.escala + folgaDoTopo(caixa) + 24;
		const maximo = Math.max(320, Math.round(window.innerHeight * 0.6));
		el.palco.style.height = `${Math.min(maximo, Math.max(260, desejada))}px`;
		caixa = el.palco.getBoundingClientRect();

		const alturaEscalada = vista.altura * vista.escala;
		vista.x = (caixa.width - vista.largura * vista.escala) / 2;
		// Árvore baixa centralizada na vertical; alta, encostada abaixo da barra de
		// controles, que flutua sobre o palco.
		vista.y =
			alturaEscalada + folgaDoTopo(caixa) < caixa.height
				? (caixa.height - alturaEscalada + folgaDoTopo(caixa)) / 2
				: folgaDoTopo(caixa);
		aplicarTransform();
	}

	function folgaDoTopo(caixa) {
		let folga = 16;
		const controles = document.querySelector(".admin-arvore__controles");
		if (controles) {
			folga = Math.max(folga, controles.getBoundingClientRect().bottom - caixa.top + 12);
		}
		return folga;
	}

	/** Converte um ponto da tela para as coordenadas do desenho. */
	function paraCanvas(clientX, clientY) {
		const el = elArvore();
		if (!el || !el.canvas) return { x: 0, y: 0 };
		const caixa = el.canvas.getBoundingClientRect();
		return {
			x: (clientX - caixa.left) / vista.escala,
			y: (clientY - caixa.top) / vista.escala,
		};
	}

	function filhosPorPai() {
		const existe = new Set(unidades.map((u) => u.name));
		const mapa = new Map();
		const raizes = [];
		unidades.forEach((u) => {
			const pai = u.responde_para && existe.has(u.responde_para) ? u.responde_para : null;
			if (pai) {
				if (!mapa.has(pai)) mapa.set(pai, []);
				mapa.get(pai).push(u);
			} else {
				raizes.push(u);
			}
		});
		return { mapa: mapa, raizes: raizes, existe: existe };
	}

	// Layout de árvore clássico: a largura de cada nó é a soma das larguras dos
	// filhos, e o pai fica centrado sobre eles. Áreas órfãs (cujo pai foi apagado)
	// entram como raiz para não sumirem do desenho.
	function calcularLayout() {
		const { mapa, raizes, existe } = filhosPorPai();
		const ordenar = (lista) =>
			lista
				.slice()
				.sort((a, b) => (a.ordem || 0) - (b.ordem || 0) || a.area.localeCompare(b.area));

		const posicoes = new Map();
		const visitados = new Set();
		let cursor = 0;

		function medir(no, profundidade) {
			// Guarda contra ciclo remanescente em dado legado: o controller barra na
			// gravação, mas o desenho não pode travar por causa disso.
			if (visitados.has(no.name)) return 0;
			visitados.add(no.name);

			const meus = colapsados.has(no.name) ? [] : ordenar(mapa.get(no.name) || []);
			const y = profundidade * (ALTURA + GAP_Y);

			if (!meus.length) {
				const x = cursor;
				cursor += LARGURA + GAP_X;
				posicoes.set(no.name, { x: x, y: y });
				return x;
			}

			const centros = meus.map((filho) => medir(filho, profundidade + 1));
			const x = (centros[0] + centros[centros.length - 1]) / 2;
			posicoes.set(no.name, { x: x, y: y });
			return x;
		}

		ordenar(raizes).forEach((no) => medir(no, 0));
		return { posicoes: posicoes, filhos: mapa, existe: existe };
	}

	function contarDescendentes(nome, mapa) {
		const filhos = mapa.get(nome) || [];
		return filhos.reduce(
			(total, filho) => total + 1 + contarDescendentes(filho.name, mapa),
			0
		);
	}

	/** Caminho ortogonal: desce, atravessa, desce. Sem curva. */
	function caminhoDaAresta(pai, filho) {
		const x1 = pai.x + LARGURA / 2;
		const y1 = pai.y + ALTURA;
		const x2 = filho.x + LARGURA / 2;
		const y2 = filho.y;
		const meio = y1 + (y2 - y1) / 2;
		return `M ${x1} ${y1} V ${meio} H ${x2} V ${y2}`;
	}

	function renderizarArvore() {
		const el = elArvore();
		if (!el || !el.cards || !el.svg || !el.canvas) return;

		const { posicoes, filhos, existe } = calcularLayout();

		let maxX = 0;
		let maxY = 0;
		posicoes.forEach((p) => {
			maxX = Math.max(maxX, p.x + LARGURA);
			maxY = Math.max(maxY, p.y + ALTURA);
		});
		vista.largura = maxX + 40;
		vista.altura = maxY + 40;
		el.canvas.style.width = `${vista.largura}px`;
		el.canvas.style.height = `${vista.altura}px`;
		el.svg.setAttribute("viewBox", `0 0 ${vista.largura} ${vista.altura}`);
		el.svg.setAttribute("width", vista.largura);
		el.svg.setAttribute("height", vista.altura);

		el.cards.innerHTML = unidades
			.map((u) => {
				const pos = posicoes.get(u.name);
				if (!pos) return "";

				const quantos = contarDescendentes(u.name, filhos);
				const temFilhos = (filhos.get(u.name) || []).length > 0;
				const retraido = colapsados.has(u.name);
				const toggle = temFilhos
					? `<button type="button" class="admin-arvore__toggle" data-acao="alternar" data-name="${escapeHtml(
							u.name
					  )}" aria-expanded="${retraido ? "false" : "true"}" aria-label="${
							retraido ? "Expandir" : "Retrair"
					  } ${escapeHtml(u.area)}">${icone(
							retraido ? "chevron-down" : "chevron-up",
							"xs"
					  )}${retraido ? `<span>${quantos}</span>` : ""}</button>`
					: "";
				const adicionar = PODE_EDITAR
					? `<button type="button" class="admin-arvore__add" data-acao="novo-filho" data-name="${escapeHtml(
							u.name
					  )}" aria-label="Nova área sob ${escapeHtml(u.area)}">${icone(
							"plus"
					  )}</button>`
					: "";

				return `<article class="admin-arvore__card${u.ativa ? "" : " is-inativa"}"
					data-name="${escapeHtml(u.name)}"
					style="left:${pos.x}px; top:${pos.y}px; width:${LARGURA}px; height:${ALTURA}px;">
					<h3 class="admin-arvore__titulo">${escapeHtml(u.area)}</h3>
					<p class="admin-arvore__sub">${escapeHtml(u.responsavel_nome || "Sem responsável")}</p>
					<p class="admin-arvore__meta">${u.funcoes.length} função(ões)</p>
					${toggle}
					${adicionar}
				</article>`;
			})
			.join("");

		el.svg.innerHTML = unidades
			.map((u) => {
				if (!u.responde_para || !existe.has(u.responde_para)) return "";
				const filho = posicoes.get(u.name);
				const pai = posicoes.get(u.responde_para);
				if (!filho || !pai) return "";

				const d = caminhoDaAresta(pai, filho);
				const x1 = pai.x + LARGURA / 2;
				const y1 = pai.y + ALTURA + FOLGA_PONTA_PAI;
				const x2 = filho.x + LARGURA / 2;
				const y2 = filho.y - FOLGA_PONTA_FILHO;
				// A ponta que se arrasta é a do pai: soltá-la sobre outra área é o que
				// troca o "responde para" desta unidade.
				const alca = PODE_EDITAR
					? `<circle class="admin-arvore__ponta admin-arvore__ponta--pai" data-alca="${escapeHtml(
							u.name
					  )}" cx="${x1}" cy="${y1}" r="6"></circle>`
					: `<circle class="admin-arvore__ponta" cx="${x1}" cy="${y1}" r="5"></circle>`;

				return `<g class="admin-arvore__aresta" data-filho="${escapeHtml(u.name)}">
					<path class="admin-arvore__linha" d="${d}"></path>
					<path class="admin-arvore__hit" d="${d}"></path>
					<circle class="admin-arvore__ponta admin-arvore__ponta--filho" cx="${x2}" cy="${y2}" r="5"></circle>
					${alca}
				</g>`;
			})
			.join("");

		// O desenho é refeito do zero a cada render: devolve o estado de seleção.
		if (arestaSelecionada) {
			const nome = arestaSelecionada;
			arestaSelecionada = null;
			selecionarAresta(nome);
		}
	}

	// ------------------------------------------------------------------
	// Navegação: zoom, pan e retrair
	// ------------------------------------------------------------------

	function todosComFilhos() {
		const { mapa } = filhosPorPai();
		return [...mapa.keys()];
	}

	function alternarTudo() {
		const comFilhos = todosComFilhos();
		const todosRetraidos = comFilhos.length > 0 && comFilhos.every((n) => colapsados.has(n));
		colapsados.clear();
		if (!todosRetraidos) comFilhos.forEach((n) => colapsados.add(n));
		atualizarRotuloRetrair();
		renderizarArvore();
		ajustarATela();
	}

	function atualizarRotuloRetrair() {
		const botao = document.querySelector('[data-zoom="retrair"]');
		if (!botao) return;
		const comFilhos = todosComFilhos();
		const todosRetraidos = comFilhos.length > 0 && comFilhos.every((n) => colapsados.has(n));
		const texto = botao.querySelector(".admin-arvore__acao-texto");
		if (texto) texto.textContent = todosRetraidos ? "Expandir tudo" : "Retrair tudo";
		botao.setAttribute("aria-label", todosRetraidos ? "Expandir tudo" : "Retrair tudo");
	}

	function ligarNavegacao() {
		const el = elArvore();
		if (!el || !el.palco) return;

		el.painel.addEventListener("click", function (evento) {
			const botao = evento.target.closest("[data-zoom]");
			if (!botao) return;
			const acao = botao.dataset.zoom;
			if (acao === "mais") definirEscala(vista.escala * 1.2);
			else if (acao === "menos") definirEscala(vista.escala / 1.2);
			else if (acao === "retrair") alternarTudo();
			else ajustarATela();
		});

		// Zoom pela roda do mouse, ancorado no cursor.
		el.palco.addEventListener(
			"wheel",
			function (evento) {
				evento.preventDefault();
				const fator = Math.pow(0.999, evento.deltaY);
				definirEscala(vista.escala * fator, evento.clientX, evento.clientY);
			},
			{ passive: false }
		);

		// Arrastar o fundo move o desenho. Começar sobre card, alça ou controles não.
		let pan = null;
		el.palco.addEventListener("pointerdown", function (evento) {
			// Linha de fora: capturar o ponteiro aqui faria o `click` ser entregue ao
			// palco em vez da aresta, e o clique que seleciona a linha nunca chegaria.
			if (
				evento.target.closest(".admin-arvore__card") ||
				evento.target.closest(".admin-arvore__aresta") ||
				evento.target.closest(".admin-arvore__controles")
			) {
				return;
			}
			pan = { x: evento.clientX - vista.x, y: evento.clientY - vista.y };
			el.palco.setPointerCapture(evento.pointerId);
			el.palco.classList.add("is-movendo");
		});
		el.palco.addEventListener("pointermove", function (evento) {
			if (!pan) return;
			vista.x = evento.clientX - pan.x;
			vista.y = evento.clientY - pan.y;
			aplicarTransform();
		});
		const soltarPan = function () {
			pan = null;
			el.palco.classList.remove("is-movendo");
		};
		el.palco.addEventListener("pointerup", soltarPan);
		el.palco.addEventListener("pointercancel", soltarPan);

		// A aba nasce escondida e `clientWidth` seria 0: o ajuste espera a aba abrir.
		document.querySelectorAll('#admin-unidades-tabs [role="tab"]').forEach((aba) => {
			aba.addEventListener("click", () => setTimeout(ajustarATela, 60));
		});
		window.addEventListener("resize", ajustarATela);
	}

	//: Filho da aresta selecionada. Religar uma área é uma decisão, não um gesto de
	//: passagem: só depois de clicar na linha as bolinhas aparecem e a de cima pode
	//: ser arrastada.
	let arestaSelecionada = null;

	function arestaDe(nome) {
		const el = elArvore();
		if (!el || !el.svg || !nome) return null;
		return (
			[...el.svg.querySelectorAll(".admin-arvore__aresta")].find(
				(g) => g.dataset.filho === nome
			) || null
		);
	}

	function cardDe(nome) {
		const el = elArvore();
		if (!el || !el.cards || !nome) return null;
		return (
			[...el.cards.querySelectorAll(".admin-arvore__card")].find(
				(c) => c.dataset.name === nome
			) || null
		);
	}

	function limparSelecao() {
		const el = elArvore();
		if (!el || !el.painel) return;
		el.painel.querySelectorAll(".admin-arvore__aresta.is-selecionada").forEach((g) => {
			g.classList.remove("is-selecionada", "is-ponta-sob");
		});
		// O "+" do card pai volta a aparecer no hover.
		el.painel.querySelectorAll(".admin-arvore__card.is-sem-add").forEach((c) => {
			c.classList.remove("is-sem-add");
		});
		arestaSelecionada = null;
	}

	function selecionarAresta(nome) {
		limparSelecao();
		const aresta = arestaDe(nome);
		if (!aresta) return;

		// Sobe a aresta para o fim do SVG: as alças de todos os filhos de um mesmo
		// pai ficam no mesmo ponto, e é a de cima que o ponteiro alcança.
		if (aresta.parentNode && aresta.nextSibling) aresta.parentNode.appendChild(aresta);
		aresta.classList.add("is-selecionada");
		arestaSelecionada = nome;

		// A bolinha de cima fica exatamente onde mora o botão "+" do pai. Enquanto a
		// linha está selecionada, o "+" sai do caminho para o arraste poder começar.
		const unidade = porNome(nome);
		const pai = unidade && cardDe(unidade.responde_para);
		if (pai) pai.classList.add("is-sem-add");
	}

	/** Realce da aresta sob o ponteiro, e do card que ela liga.
	 *
	 * Por classe, e não por `:hover` no CSS: o `:hover` não chega ao `<g>` do SVG de
	 * forma confiável, e classe ainda funciona no toque, onde hover não existe.
	 */
	function ligarRealceDasArestas() {
		const el = elArvore();
		if (!el || !el.svg || !el.cards) return;

		el.svg.addEventListener("pointerover", function (evento) {
			const aresta = evento.target.closest(".admin-arvore__aresta");
			if (!aresta) return;
			aresta.classList.add("is-sob");
			if (evento.target.closest("[data-alca]")) aresta.classList.add("is-ponta-sob");
		});

		el.svg.addEventListener("pointerout", function (evento) {
			const aresta = evento.target.closest(".admin-arvore__aresta");
			if (!aresta || aresta.classList.contains("is-arrastando")) return;
			const indo = evento.relatedTarget;
			if (indo && aresta.contains(indo)) {
				// Só trocou de filho dentro da mesma aresta.
				if (!indo.closest("[data-alca]")) aresta.classList.remove("is-ponta-sob");
				return;
			}
			aresta.classList.remove("is-sob");
			if (aresta.dataset.filho !== arestaSelecionada)
				aresta.classList.remove("is-ponta-sob");
		});

		// Passar o mouse num card acende também a linha que o liga ao pai.
		el.cards.addEventListener("pointerover", function (evento) {
			const card = evento.target.closest(".admin-arvore__card");
			if (!card) return;
			const aresta = arestaDe(card.dataset.name);
			if (aresta) aresta.classList.add("is-sob");
		});

		el.cards.addEventListener("pointerout", function (evento) {
			const card = evento.target.closest(".admin-arvore__card");
			if (!card) return;
			const indo = evento.relatedTarget;
			if (indo && card.contains(indo)) return;
			const aresta = arestaDe(card.dataset.name);
			if (aresta && !aresta.classList.contains("is-arrastando"))
				aresta.classList.remove("is-sob");
		});

		// Clicar na linha seleciona; clicar no vazio do palco desfaz.
		el.svg.addEventListener("click", function (evento) {
			const aresta = evento.target.closest(".admin-arvore__aresta");
			if (!aresta) return;
			evento.stopPropagation();
			if (aresta.dataset.filho === arestaSelecionada) limparSelecao();
			else selecionarAresta(aresta.dataset.filho);
		});

		el.palco.addEventListener("pointerdown", function (evento) {
			if (evento.target.closest(".admin-arvore__aresta")) return;
			limparSelecao();
		});

		el.palco.addEventListener("keydown", function (evento) {
			if (evento.key === "Escape") limparSelecao();
		});
	}

	// Arrastar a ponta da linha presa ao pai e soltar sobre outra área.
	function ligarArraste() {
		if (!PODE_EDITAR) return;
		const el = elArvore();
		if (!el || !el.painel) return;

		let arrasto = null;

		function limparAlvo() {
			el.painel.querySelectorAll(".admin-arvore__card.is-alvo").forEach((card) => {
				card.classList.remove("is-alvo");
			});
		}

		el.painel.addEventListener("pointerdown", function (evento) {
			const alca = evento.target.closest("[data-alca]");
			if (!alca) return;
			evento.preventDefault();
			evento.stopPropagation();

			const filho = alca.dataset.alca;
			const aresta = alca.closest(".admin-arvore__aresta");
			// Só a linha selecionada se arrasta. O CSS já tira o ponteiro das outras,
			// mas a regra vale aqui também para não depender só dele.
			if (!aresta || filho !== arestaSelecionada) return;
			const pontaFilho = aresta.querySelector(".admin-arvore__ponta--filho");
			if (!pontaFilho) return;

			arrasto = {
				filho: filho,
				aresta: aresta,
				linha: aresta.querySelector(".admin-arvore__linha"),
				hit: aresta.querySelector(".admin-arvore__hit"),
				alca: alca,
				destinoX: Number(pontaFilho.getAttribute("cx")),
				destinoY: Number(pontaFilho.getAttribute("cy")),
			};
			aresta.classList.add("is-arrastando");
			aresta.classList.add("is-sob");
			el.painel.classList.add("is-arrastando");
			alca.setPointerCapture(evento.pointerId);
		});

		el.painel.addEventListener("pointermove", function (evento) {
			if (!arrasto) return;
			// A linha acompanha o cursor: sem isso o arraste não dá nenhum sinal de
			// que está acontecendo até o momento de soltar.
			const ponto = paraCanvas(evento.clientX, evento.clientY);
			const d = `M ${ponto.x} ${ponto.y} L ${arrasto.destinoX} ${arrasto.destinoY}`;
			arrasto.linha.setAttribute("d", d);
			arrasto.hit.setAttribute("d", d);
			arrasto.alca.setAttribute("cx", ponto.x);
			arrasto.alca.setAttribute("cy", ponto.y);

			limparAlvo();
			const sob = document.elementFromPoint(evento.clientX, evento.clientY);
			const candidato = sob && sob.closest(".admin-arvore__card");
			if (candidato && candidato.dataset.name !== arrasto.filho) {
				candidato.classList.add("is-alvo");
			}
		});

		el.painel.addEventListener("pointerup", async function (evento) {
			if (!arrasto) return;
			const filho = arrasto.filho;
			arrasto = null;
			el.painel.classList.remove("is-arrastando");
			limparAlvo();

			// O ponteiro está capturado pela alça, então `event.target` não serve:
			// quem está sob o cursor vem do hit-test explícito.
			const sob = document.elementFromPoint(evento.clientX, evento.clientY);
			const destino = sob && sob.closest(".admin-arvore__card");
			const atual = porNome(filho);
			const novoPai = destino && destino.dataset.name;

			if (!destino || !atual || novoPai === filho || atual.responde_para === novoPai) {
				// Sem destino novo, o desenho volta ao lugar.
				renderizarArvore();
				return;
			}

			try {
				aplicar(
					await chamar("gris.api.administracao.mover_unidade", {
						name: filho,
						responde_para: novoPai,
					})
				);
				toast("success", `${atual.area} agora responde para ${novoPai}.`);
			} catch (erro) {
				renderizarArvore();
				toast("error", erro.message);
			}
		});
	}

	// ------------------------------------------------------------------
	// Dialog de criação/edição
	// ------------------------------------------------------------------

	function definirComponente(id, valor) {
		// Select e combobox expõem `value` na raiz; escrever no hidden não atualiza
		// o rótulo visível.
		const elemento = document.getElementById(id);
		if (elemento) elemento.value = valor || "";
	}

	function valorDoSelect(id) {
		const elemento = document.getElementById(id);
		if (!elemento) return "";
		const hidden = elemento.querySelector('input[type="hidden"]');
		return hidden ? hidden.value : "";
	}

	/** O switch do design system põe o id no rótulo, não no checkbox. */
	function switchDe(id) {
		const rotulo = document.getElementById(id);
		return rotulo ? rotulo.querySelector('input[type="checkbox"]') : null;
	}

	// A primeira opção é sempre um placeholder de valor vazio: ao inicializar, o
	// select seleciona sozinho a primeira opção, e em silêncio, sem disparar
	// `change`.
	function repopularSelect(id, itens, placeholder, selecionado) {
		const antigo = document.getElementById(id);
		if (!antigo) return;
		const listbox = antigo.querySelector('[role="listbox"]');
		const hidden = antigo.querySelector('input[type="hidden"]');
		const rotulo = antigo.querySelector(":scope > button > span");
		if (!listbox || !hidden || !rotulo) return;

		const texto = placeholder == null ? "Selecione…" : placeholder;
		antigo.dataset.placeholder = texto;
		listbox.innerHTML = "";
		[{ value: "", label: texto }, ...(itens || [])].forEach((item, indice) => {
			const opcao = document.createElement("div");
			opcao.id = `${id}-items-${indice + 1}`;
			opcao.setAttribute("role", "option");
			opcao.dataset.value = item.value;
			opcao.textContent = item.label;
			if (selecionado && item.value === selecionado)
				opcao.setAttribute("aria-selected", "true");
			listbox.appendChild(opcao);
		});

		const escolhido = (itens || []).find((i) => i.value === selecionado);
		hidden.value = escolhido ? escolhido.value : "";
		rotulo.textContent = escolhido ? escolhido.label : texto;

		const novo = antigo.cloneNode(true);
		novo.removeAttribute("data-select-initialized");
		antigo.parentNode.replaceChild(novo, antigo);
	}

	function renderizarFuncoesDoDialog() {
		const corpo = document.getElementById("area-funcoes-corpo");
		if (!corpo) return;
		if (!funcoesNoDialog.length) {
			corpo.innerHTML =
				'<tr><td colspan="2" class="text-muted-foreground text-sm">Nenhuma função vinculada.</td></tr>';
			return;
		}
		corpo.innerHTML = funcoesNoDialog
			.map(
				(f, indice) => `<tr>
					<td>${escapeHtml(f.funcao)}</td>
					<td class="admin-dialog__acoes">
						<button type="button" class="btn-sm-ghost" data-acao="remover-funcao" data-indice="${indice}">Remover</button>
					</td>
				</tr>`
			)
			.join("");
	}

	function abrirDialog(unidade, paiSugerido) {
		if (!dialogArea) return;
		const nova = !unidade;
		const automatica = !nova && unidade.origem_automatica;

		document.getElementById("area-name").value = nova ? "" : unidade.name;
		document.getElementById("area-nome").value = nova ? "" : unidade.area;
		document.getElementById("area-nome").disabled = automatica;
		document.getElementById("area-ordem").value = nova ? 0 : unidade.ordem;
		document.getElementById("area-descricao").value = nova ? "" : unidade.descricao || "";

		const ativa = switchDe("area-ativa");
		if (ativa) {
			ativa.checked = nova ? true : unidade.ativa;
			ativa.disabled = automatica;
		}

		const aviso = document.getElementById("area-aviso-automatica");
		if (aviso) aviso.hidden = !automatica;

		// A própria área não pode ser o pai dela.
		const candidatos = unidades
			.filter((u) => nova || u.name !== unidade.name)
			.map((u) => ({ value: u.name, label: u.area }));
		repopularSelect(
			"area-responde-para",
			candidatos,
			"Nenhuma (área de topo)",
			nova ? paiSugerido || "" : unidade.responde_para || ""
		);
		definirComponente("area-responsavel", nova ? "" : unidade.responsavel || "");

		funcoesNoDialog = nova ? [] : unidade.funcoes.map((f) => ({ ...f }));
		renderizarFuncoesDoDialog();
		repopularSelect("area-nova-funcao", opcoesFuncao, "Escolha a função…");

		dialogArea.showModal();
	}

	async function salvar(botao) {
		const ativa = switchDe("area-ativa");
		const payload = {
			name: document.getElementById("area-name").value,
			area: document.getElementById("area-nome").value.trim(),
			responde_para: valorDoSelect("area-responde-para"),
			responsavel: valorDoSelect("area-responsavel"),
			ordem: document.getElementById("area-ordem").value,
			descricao: document.getElementById("area-descricao").value.trim(),
			ativa: ativa ? ativa.checked : true,
			funcoes: funcoesNoDialog,
		};
		if (!payload.area) {
			toast("error", "Informe o nome da área.");
			return;
		}

		botao.disabled = true;
		try {
			aplicar(await chamar("gris.api.administracao.salvar_unidade", payload));
			dialogArea.close();
			toast("success", payload.name ? "Área atualizada." : "Área criada.");
		} catch (erro) {
			toast("error", erro.message);
		} finally {
			botao.disabled = false;
		}
	}

	// ------------------------------------------------------------------
	// Ligações
	// ------------------------------------------------------------------

	function renderizarTudo() {
		renderizarTabela();
		renderizarArvore();
		atualizarRotuloRetrair();
		ajustarATela();
	}

	document.addEventListener("click", function (evento) {
		const cancelar = evento.target.closest("[data-dialog-cancel]");
		if (cancelar) {
			document.getElementById(cancelar.dataset.dialogCancel)?.close();
			return;
		}

		if (evento.target.closest("#btn-nova-area")) {
			abrirDialog(null, "");
			return;
		}

		const salvarBtn = evento.target.closest("#btn-salvar-area");
		if (salvarBtn) {
			salvar(salvarBtn);
			return;
		}

		if (evento.target.closest("#btn-add-funcao-area")) {
			const escolhida = valorDoSelect("area-nova-funcao");
			if (!escolhida) {
				toast("error", "Escolha a função.");
				return;
			}
			if (funcoesNoDialog.some((f) => f.funcao === escolhida)) {
				toast("error", "Essa função já está na lista.");
				return;
			}
			funcoesNoDialog.push({ funcao: escolhida, observacao: "" });
			renderizarFuncoesDoDialog();
			repopularSelect("area-nova-funcao", opcoesFuncao, "Escolha a função…");
			return;
		}

		const acao = evento.target.closest("[data-acao]");
		if (!acao) return;

		if (acao.dataset.acao === "editar") {
			abrirDialog(porNome(acao.dataset.name));
		} else if (acao.dataset.acao === "novo-filho") {
			abrirDialog(null, acao.dataset.name);
		} else if (acao.dataset.acao === "remover-funcao") {
			funcoesNoDialog.splice(Number(acao.dataset.indice), 1);
			renderizarFuncoesDoDialog();
		} else if (acao.dataset.acao === "alternar") {
			const nome = acao.dataset.name;
			if (colapsados.has(nome)) colapsados.delete(nome);
			else colapsados.add(nome);
			atualizarRotuloRetrair();
			renderizarArvore();
		}
	});

	// Clicar no card abre o mesmo dialog da tabela — menos nos botões dele.
	document.addEventListener("click", function (evento) {
		const card = evento.target.closest(".admin-arvore__card");
		if (!card || evento.target.closest("[data-acao]") || evento.target.closest("[data-alca]"))
			return;
		if (!PODE_EDITAR) return;
		abrirDialog(porNome(card.dataset.name));
	});

	/** No celular a árvore não cabe: a tabela é a visão útil.
	 *
	 * O clique só vale depois que o componente de abas se inicializa — quem escuta o
	 * `click` é ele, e a inicialização vem do observador do design system, que roda
	 * depois deste script.
	 */
	function escolherAbaInicial() {
		if (!window.matchMedia("(max-width: 768px)").matches) return;
		const abas = document.getElementById("admin-unidades-tabs");
		if (!abas) return;

		const trocar = () => {
			const abaTabela = abas.querySelector('[role="tab"]');
			if (abaTabela) abaTabela.click();
		};

		if (abas.dataset.tabsInitialized) trocar();
		else abas.addEventListener("basecoat:initialized", trocar, { once: true });
	}

	renderizarTudo();
	ligarNavegacao();
	ligarRealceDasArestas();
	ligarArraste();
	escolherAbaInicial();
})();
