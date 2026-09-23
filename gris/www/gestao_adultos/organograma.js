// Organograma da Gestão de Adultos.
// Árvore em <ul>/<li> aninhados, com pan e zoom aplicados por transform no
// canvas — os cards não se movem entre si, só a posição do desenho na tela.

frappe.ready(() => {
	const ZOOM_MIN = 0.3;
	const ZOOM_MAX = 2;
	const ZOOM_PASSO = 0.15;
	// Folga mínima no topo do enquadramento; o valor real sai da altura do filtro
	// e dos controles, que flutuam sobre o canvas.
	const FOLGA_MINIMA = 24;

	const el = {
		loading: document.getElementById("organograma-loading"),
		erro: document.getElementById("organograma-erro"),
		vazio: document.getElementById("organograma-vazio"),
		recarregando: document.getElementById("organograma-recarregando"),
		viewport: document.getElementById("organograma-viewport"),
		canvas: document.getElementById("organograma-canvas"),
		avisos: document.getElementById("organograma-avisos"),
		dica: document.getElementById("organograma-dica"),
		nivel: document.getElementById("organograma-zoom-nivel"),
		menos: document.getElementById("organograma-zoom-menos"),
		mais: document.getElementById("organograma-zoom-mais"),
		ajustar: document.getElementById("organograma-ajustar"),
		expandir: document.getElementById("organograma-expandir"),
		filtro: document.getElementById("filtro-area"),
		palco: document.getElementById("organograma-palco"),
		detalhe: document.getElementById("organograma-detalhe"),
		detalheFechar: document.getElementById("detalhe-fechar"),
		detalheCarregando: document.getElementById("detalhe-carregando"),
		detalheErro: document.getElementById("detalhe-erro"),
		detalheConteudo: document.getElementById("detalhe-conteudo"),
	};

	if (!el.viewport || !el.canvas) {
		return;
	}

	const vista = { x: 0, y: 0, escala: 1 };
	let tudoExpandido = true;
	let detalheAberto = null;

	ligarFiltro();
	ligarDetalhe();
	carregar();

	async function carregar(area) {
		// Na troca de filtro o painel continua na tela: ele é que hospeda o
		// seletor, e escondê-lo tiraria do usuário a forma de desfazer o filtro.
		const primeiraCarga = el.viewport.hidden;
		if (primeiraCarga) {
			mostrarPainel(el.loading);
		} else if (el.recarregando) {
			el.recarregando.hidden = false;
		}

		try {
			const resposta = await frappe.call({
				method: "gris.api.gestao_adultos.obter_organograma",
				args: { area: area || "" },
			});
			render(resposta.message || {});
		} catch (erro) {
			console.error("Falha ao carregar o organograma.", erro);
			if (primeiraCarga) {
				mostrarPainel(el.erro);
			} else {
				avisarFalhaDoFiltro();
			}
		} finally {
			if (el.recarregando) {
				el.recarregando.hidden = true;
			}
		}
	}

	function mostrarPainel(alvo) {
		[el.loading, el.erro, el.viewport].forEach((n) => {
			if (n) {
				n.hidden = n !== alvo;
			}
		});
		if (el.dica) {
			el.dica.hidden = alvo !== el.viewport;
		}
	}

	function avisarFalhaDoFiltro() {
		if (!el.avisos) {
			return;
		}
		el.avisos.hidden = false;
		el.avisos.innerHTML = `
			<div class="alert alert-destructive" role="alert">
				<h2>Não foi possível aplicar o filtro</h2>
				<section>O organograma continua mostrando o resultado anterior. Tente de novo.</section>
			</div>`;
	}

	function ligarFiltro() {
		if (!el.filtro) {
			return;
		}
		el.filtro.addEventListener("change", (evento) => {
			const valor = evento.detail ? evento.detail.value : el.filtro.value;
			carregar(Array.isArray(valor) ? valor[0] || "" : valor || "");
		});
	}

	function render(dados) {
		const raizes = dados.raizes || [];
		const semArea = dados.sem_area;

		renderAvisos(dados.avisos || {});
		mostrarPainel(el.viewport);
		// A árvore é recriada do zero: o nó que estava aberto pode nem existir mais.
		fecharDetalhe();

		el.canvas.innerHTML = "";
		if (raizes.length) {
			el.canvas.appendChild(arvore(raizes));
		}
		if (semArea) {
			const bloco = document.createElement("div");
			bloco.className = "organograma-bloco-solto";
			bloco.appendChild(arvore([semArea]));
			el.canvas.appendChild(bloco);
		}

		if (el.vazio) {
			el.vazio.hidden = Boolean(raizes.length || semArea);
		}
		tudoExpandido = true;
		atualizarRotuloExpandir();

		ligarInteracoes();
		ajustarATela();
	}

	function renderAvisos(avisos) {
		if (!el.avisos) {
			return;
		}
		const partes = [];
		if (avisos.pessoas_sem_area) {
			partes.push(
				`${avisos.pessoas_sem_area} ${
					avisos.pessoas_sem_area === 1 ? "pessoa está" : "pessoas estão"
				} sem área definida.`
			);
		}
		if ((avisos.areas_sem_responsavel || []).length) {
			partes.push(`Sem responsável: ${avisos.areas_sem_responsavel.join(", ")}.`);
		}
		if (avisos.funcoes_sem_area) {
			partes.push(
				`${avisos.funcoes_sem_area} ${
					avisos.funcoes_sem_area === 1
						? "função atribuída não tem"
						: "funções atribuídas não têm"
				} área mapeada.`
			);
		}
		if ((avisos.ciclos || []).length) {
			partes.push(`Hierarquia circular detectada em: ${avisos.ciclos.join(", ")}.`);
		}

		if (!partes.length) {
			el.avisos.hidden = true;
			el.avisos.innerHTML = "";
			return;
		}

		el.avisos.hidden = false;
		el.avisos.innerHTML = `
			<div class="alert" role="status">
				<h2>Faltam dados para o organograma ficar completo</h2>
				<section>${escapeHtml(partes.join(" "))}</section>
			</div>`;
	}

	// -- Painel de detalhes --------------------------------------------------

	function ligarDetalhe() {
		if (!el.detalhe) {
			return;
		}
		el.detalheFechar?.addEventListener("click", fecharDetalhe);
		document.addEventListener("keydown", (evento) => {
			if (evento.key === "Escape" && detalheAberto) {
				fecharDetalhe();
			}
		});
		observarLarguraDoViewport();
	}

	function observarLarguraDoViewport() {
		if (typeof ResizeObserver === "undefined") {
			return;
		}
		let anterior = null;
		new ResizeObserver((entradas) => {
			const largura = entradas[0].contentRect.width;
			if (anterior !== null && largura !== anterior) {
				// Abrir/fechar o painel estreita o viewport. Sem compensar metade da
				// diferença, o desenho salta de lado a cada abertura.
				vista.x += (largura - anterior) / 2;
				aplicarTransform();
			}
			anterior = largura;
		}).observe(el.viewport);
	}

	function alternarDetalhe(id) {
		if (detalheAberto === id) {
			fecharDetalhe();
		} else {
			abrirDetalhe(id);
		}
	}

	async function abrirDetalhe(id) {
		if (!el.detalhe) {
			return;
		}
		detalheAberto = id;
		marcarCardAtivo(id);
		el.detalhe.hidden = false;
		el.palco?.classList.add("tem-detalhe");
		el.detalheCarregando.hidden = false;
		el.detalheErro.hidden = true;
		el.detalheConteudo.hidden = true;

		try {
			const resposta = await frappe.call({
				method: "gris.api.gestao_adultos.obter_detalhe_do_adulto",
				args: { associado: id },
			});
			// Outro card pode ter sido aberto enquanto esta resposta vinha.
			if (detalheAberto !== id) {
				return;
			}
			renderDetalhe(resposta.message || {});
			el.detalheConteudo.hidden = false;
		} catch (erro) {
			console.error("Falha ao carregar os detalhes do adulto.", erro);
			if (detalheAberto === id) {
				el.detalheErro.hidden = false;
			}
		} finally {
			if (detalheAberto === id) {
				el.detalheCarregando.hidden = true;
			}
		}
	}

	function fecharDetalhe() {
		detalheAberto = null;
		marcarCardAtivo(null);
		if (el.detalhe) {
			el.detalhe.hidden = true;
		}
		el.palco?.classList.remove("tem-detalhe");
	}

	function marcarCardAtivo(id) {
		el.canvas.querySelectorAll(".org-card[aria-current]").forEach((card) => {
			card.removeAttribute("aria-current");
		});
		if (!id) {
			return;
		}
		el.canvas
			.querySelectorAll(`.org-card[data-associado="${CSS.escape(id)}"]`)
			.forEach((card) => card.setAttribute("aria-current", "true"));
	}

	function renderDetalhe(dados) {
		const badges = [];
		if (dados.linha) {
			badges.push(`<span class="badge-primary">${escapeHtml(dados.linha)}</span>`);
		}
		if (dados.ramo) {
			const classeRamo = dados.ramo_slug ? ` badge-ramo-${dados.ramo_slug}` : "";
			badges.push(`<span class="badge${classeRamo}">${escapeHtml(dados.ramo)}</span>`);
		}
		if (dados.secao) {
			badges.push(`<span class="badge-outline">${escapeHtml(dados.secao)}</span>`);
		}

		el.detalheConteudo.innerHTML = `
			<div class="organograma-detalhe__identidade">
				${avatarHtml(dados, "organograma-detalhe__avatar")}
				<h2 class="organograma-detalhe__nome" id="detalhe-nome">${escapeHtml(dados.nome)}</h2>
				<p class="organograma-detalhe__funcao">${escapeHtml(
					dados.funcao_principal || "Sem função interna"
				)}</p>
				${badges.length ? `<div class="organograma-detalhe__badges">${badges.join("")}</div>` : ""}
			</div>
			<div class="organograma-detalhe__acoes">${acoesHtml(dados)}</div>
			${dadosHtml(dados)}
			<h3 class="organograma-detalhe__titulo-secao">Funções (${dados.funcoes.length})</h3>
			${funcoesHtml(dados.funcoes)}`;
	}

	function acoesHtml(dados) {
		const partes = [];
		const whatsapp = `
			<svg class="ds-lucide ds-lucide--sm" style="fill: currentColor; stroke: none;"
				aria-hidden="true" focusable="false" viewBox="0 0 24 24">
				<use href="/assets/gris/design_system/icons/simple-icons/sprite.svg#whatsapp" />
			</svg>`;

		if (dados.whatsapp) {
			partes.push(`
				<a class="btn-whatsapp" href="https://wa.me/${escapeHtml(dados.whatsapp)}"
					target="_blank" rel="noopener noreferrer">
					${whatsapp}<span>Enviar mensagem</span>
				</a>`);
		} else {
			// Desabilitado, e não escondido: a lacuna de cadastro fica visível.
			partes.push(`
				<button type="button" class="btn-whatsapp" disabled>
					${whatsapp}<span>Enviar mensagem</span>
				</button>
				<p class="organograma-detalhe__aviso">Sem telefone cadastrado.</p>`);
		}

		if (el.detalhe.dataset.podeAbrirFicha === "1") {
			partes.push(`
				<a class="btn-outline" href="${escapeHtml(dados.ficha_url)}">
					<svg class="ds-lucide ds-lucide--sm" aria-hidden="true" focusable="false" viewBox="0 0 24 24">
						<use href="/assets/gris/design_system/icons/lucide/sprite.svg#file-text" />
					</svg>
					<span>Abrir ficha</span>
				</a>`);
		}
		return partes.join("");
	}

	function dadosHtml(dados) {
		const areas = dados.areas || [];
		const linhas = [
			["network", areas.length > 1 ? "Áreas" : "Área", areas.join(", ")],
			["user-round", "Linha", dados.linha],
		];
		if (dados.ramo) {
			linhas.push(["flag", "Ramo", dados.ramo]);
		}
		if (dados.secao) {
			linhas.push(["tent", "Seção", dados.secao]);
		}
		const corpo = linhas
			.map(
				([icone, rotulo, valor]) =>
					`<dt>${iconeLucide(icone)}<span>${escapeHtml(rotulo)}</span></dt>` +
					`<dd>${escapeHtml(valor || "—")}</dd>`
			)
			.join("");
		return `<dl class="organograma-detalhe__dados">${corpo}</dl>`;
	}

	function iconeLucide(nome) {
		return `<svg class="ds-lucide ds-lucide--sm" aria-hidden="true" focusable="false"
			viewBox="0 0 24 24"><use href="/assets/gris/design_system/icons/lucide/sprite.svg#${nome}" /></svg>`;
	}

	function funcoesHtml(funcoes) {
		if (!funcoes.length) {
			return `<p class="organograma-detalhe__aviso">Nenhuma função interna atribuída.</p>`;
		}

		const itens = funcoes
			.map((funcao) => {
				const atribuicoes = funcao.responsabilidades.length
					? `<ul class="organograma-detalhe__atribuicoes">${funcao.responsabilidades
							.map(
								(item) =>
									`<li>${escapeHtml(item.responsabilidade)}${
										item.detalhe
											? `<span class="organograma-detalhe__atribuicao-detalhe">${escapeHtml(
													item.detalhe
											  )}</span>`
											: ""
									}</li>`
							)
							.join("")}</ul>`
					: `<p class="organograma-detalhe__sem-atribuicao">Nenhuma atribuição cadastrada para esta função.</p>`;

				return `
					<details>
						<summary>
							<span class="organograma-detalhe__funcao-texto">
								<span class="organograma-detalhe__funcao-titulo">${escapeHtml(funcao.titulo)}</span>
								<span class="organograma-detalhe__funcao-periodo">${escapeHtml(
									[funcao.area, funcao.periodo].filter(Boolean).join(" · ")
								)}</span>
							</span>
							<svg class="ds-lucide ds-lucide--sm organograma-detalhe__seta" aria-hidden="true"
								focusable="false" viewBox="0 0 24 24">
								<use href="/assets/gris/design_system/icons/lucide/sprite.svg#chevron-right" />
							</svg>
						</summary>
						${
							funcao.descricao
								? `<p class="organograma-detalhe__descricao">${escapeHtml(
										funcao.descricao
								  )}</p>`
								: ""
						}
						${atribuicoes}
					</details>`;
			})
			.join("");

		return `<div class="organograma-detalhe__funcoes accordion">${itens}</div>`;
	}

	// -- Árvore ------------------------------------------------------------

	function arvore(nos) {
		const ul = document.createElement("ul");
		ul.className = "org-tree";
		nos.forEach((no) => ul.appendChild(item(no)));
		return ul;
	}

	function item(no) {
		const li = document.createElement("li");
		li.className = "org-node";
		li.dataset.tipo = no.tipo;

		const filhos = no.children || [];
		li.appendChild(no.tipo === "grupo" ? cardGrupo(no, filhos) : cardPessoa(no, filhos));

		if (filhos.length) {
			li.classList.add("has-children");
			li.appendChild(arvore(filhos));
		}
		return li;
	}

	function cardPessoa(no, filhos) {
		const card = document.createElement("article");
		card.className = "org-card";
		card.dataset.id = no.id;
		card.dataset.associado = no.associado;
		card.tabIndex = 0;
		card.setAttribute("role", "button");
		card.setAttribute("aria-label", `Ver detalhes de ${no.nome}`);
		if (no.lidera_area) {
			card.classList.add("org-card--lider");
		}

		const badges = [];
		if (no.linha) {
			// Mesmo selo da coluna "Categoria" em /associados/lista.
			badges.push(
				`<span class="badge-primary org-card__badge">${escapeHtml(no.linha)}</span>`
			);
		}
		if (no.ramo) {
			// badge-ramo-* pinta com a cor oficial do ramo (design system).
			const classeRamo = no.ramo_slug ? ` badge-ramo-${no.ramo_slug}` : "";
			badges.push(
				`<span class="badge${classeRamo} org-card__badge">${escapeHtml(no.ramo)}</span>`
			);
		}

		card.innerHTML = `
			${no.area ? `<p class="org-card__area">${escapeHtml(no.area)}</p>` : ""}
			<div class="org-card__topo">
				${avatarHtml(no)}
				<div class="org-card__identidade">
					<p class="org-card__nome">${escapeHtml(no.nome)}</p>
					<p class="org-card__funcao">${escapeHtml(no.funcao_interna || "Sem função interna")}</p>
				</div>
			</div>
			<div class="org-card__meta">${badges.join("")}</div>
			${
				no.secao
					? `<div class="org-card__meta"><span class="badge-outline org-card__badge">${escapeHtml(
							no.secao
					  )}</span></div>`
					: ""
			}
			${outrasAreasHtml(no)}
			${liderancaHtml(no)}`;

		if (filhos.length) {
			card.appendChild(botaoToggle(filhos));
		}
		return card;
	}

	function cardGrupo(no, filhos) {
		const card = document.createElement("article");
		card.className = "org-card org-card--grupo";
		const membros = no.membros || 0;
		const contagem = `${membros} ${membros === 1 ? "pessoa" : "pessoas"}`;
		// "sem responsável" só cabe no grupo de uma área; o bloco dos que não têm
		// área nenhuma já diz isso no próprio título.
		const legenda = no.id === "sem-area" ? contagem : `${contagem} · sem responsável`;
		card.innerHTML = `
			<div class="org-card__topo">
				<span class="avatar org-card__avatar--grupo" aria-hidden="true">
					<svg class="ds-lucide ds-lucide--sm" aria-hidden="true" focusable="false" viewBox="0 0 24 24">
						<use href="/assets/gris/design_system/icons/lucide/sprite.svg#users" />
					</svg>
				</span>
				<div class="org-card__identidade">
					<p class="org-card__nome">${escapeHtml(no.nome)}</p>
					<p class="org-card__funcao">${legenda}</p>
				</div>
			</div>`;

		if (filhos.length) {
			card.appendChild(botaoToggle(filhos));
		}
		return card;
	}

	function outrasAreasHtml(no) {
		// Quem tem funções em áreas diferentes aparece em vários pontos da árvore.
		// Sem esta linha, o mesmo rosto repetido pareceria erro de renderização.
		const outras = no.outras_areas || [];
		if (!outras.length) {
			return "";
		}
		return `<p class="org-card__outras-areas">Também em ${escapeHtml(outras.join(", "))}</p>`;
	}

	function liderancaHtml(no) {
		if (!no.lidera_area) {
			return "";
		}
		const partes = [`${no.diretos} ${no.diretos === 1 ? "direto" : "diretos"}`];
		if (no.indiretos) {
			partes.push(`${no.indiretos} ${no.indiretos === 1 ? "indireto" : "indiretos"}`);
		}
		return `
			<p class="org-card__lideranca">
				<span class="org-card__area-liderada">${escapeHtml(no.lidera_area)}</span>
				<span>${partes.join(" · ")}</span>
			</p>`;
	}

	function avatarHtml(no, classeExtra = "") {
		// Mesma marcação da macro `avatar` do design system. O nome já aparece ao
		// lado, então a imagem entra como decorativa e as iniciais ficam ocultas
		// para o leitor de tela — senão o card é anunciado duas vezes.
		const classes = `avatar${classeExtra ? ` ${classeExtra}` : ""}`;
		if (no.avatar_url) {
			return `<span class="${classes}"><img src="${escapeHtml(
				no.avatar_url
			)}" alt="" draggable="false"></span>`;
		}
		return `<span class="${classes}"><span aria-hidden="true">${escapeHtml(
			no.iniciais || "?"
		)}</span></span>`;
	}

	function botaoToggle(filhos) {
		const pessoas = contarPessoas(filhos);
		const botao = document.createElement("button");
		botao.type = "button";
		botao.className = "org-card__toggle";
		botao.setAttribute("aria-expanded", "true");
		botao.dataset.pessoas = String(pessoas);
		botao.innerHTML = iconeToggle("chevron-down");
		botao.addEventListener("click", (evento) => {
			evento.stopPropagation();
			alternar(botao);
		});
		return botao;
	}

	function iconeToggle(nome) {
		return `<svg class="ds-lucide ds-lucide--sm" aria-hidden="true" focusable="false" viewBox="0 0 24 24">
			<use href="/assets/gris/design_system/icons/lucide/sprite.svg#${nome}" /></svg>`;
	}

	function alternar(botao, forcarRetraido, ancorar = true) {
		const li = botao.closest(".org-node");
		if (!li) {
			return;
		}
		const retrair =
			forcarRetraido === undefined ? !li.classList.contains("is-collapsed") : forcarRetraido;

		// A árvore muda de tamanho, e como a posição vem de um translate fixo o
		// desenho inteiro escorregaria. Prender o card clicado no lugar mantém a
		// referência visual de quem está navegando.
		const antes = ancorar ? botao.getBoundingClientRect() : null;

		li.classList.toggle("is-collapsed", retrair);
		botao.setAttribute("aria-expanded", String(!retrair));
		botao.innerHTML = iconeToggle(retrair ? "chevron-right" : "chevron-down");

		const pessoas = Number(botao.dataset.pessoas || 0);
		botao.setAttribute(
			"aria-label",
			retrair
				? `Expandir e mostrar ${pessoas} ${pessoas === 1 ? "pessoa" : "pessoas"}`
				: "Retrair este ramo"
		);
		botao.title = botao.getAttribute("aria-label");

		if (antes) {
			const depois = botao.getBoundingClientRect();
			vista.x += antes.left - depois.left;
			vista.y += antes.top - depois.top;
			aplicarTransform();
		}
	}

	function contarPessoas(nos) {
		return (nos || []).reduce(
			(total, no) => total + (no.tipo === "pessoa" ? 1 : 0) + contarPessoas(no.children),
			0
		);
	}

	// -- Pan, zoom e controles ---------------------------------------------

	function aplicarTransform() {
		el.canvas.style.transform = `translate(${vista.x}px, ${vista.y}px) scale(${vista.escala})`;
		if (el.nivel) {
			el.nivel.textContent = `${Math.round(vista.escala * 100)}%`;
		}
	}

	function definirEscala(novaEscala, ancoraX, ancoraY) {
		const limitada = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, novaEscala));
		if (limitada === vista.escala) {
			return;
		}
		const caixa = el.viewport.getBoundingClientRect();
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
		// offsetWidth/Height dão o tamanho de layout; getBoundingClientRect devolveria
		// a caixa já transformada (e ainda no meio da transição), o que faria a escala
		// ser calculada em cima dela mesma.
		const largura = el.canvas.offsetWidth;
		const altura = el.canvas.offsetHeight;
		const caixa = el.viewport.getBoundingClientRect();
		if (!largura || !altura || !caixa.width || !caixa.height) {
			return;
		}

		const escala = Math.min(
			ZOOM_MAX,
			Math.max(ZOOM_MIN, Math.min(caixa.width / largura, caixa.height / altura) * 0.95)
		);
		const alturaEscalada = altura * escala;
		vista.escala = escala;
		vista.x = (caixa.width - largura * escala) / 2;
		// Árvore baixa centralizada na vertical: encostada no topo, o centro do
		// viewport cai no vazio e o zoom pelos botões empurra o desenho para fora.
		vista.y =
			alturaEscalada < caixa.height
				? (caixa.height - alturaEscalada) / 2
				: folgaDoTopo(caixa);
		aplicarTransform();
	}

	function folgaDoTopo(caixa) {
		// A barra de controles flutua sobre o canvas e muda de altura entre desktop
		// e mobile; medir evita a árvore nascer escondida atrás dela.
		let folga = FOLGA_MINIMA;
		el.viewport.querySelectorAll(".organograma-controles").forEach((node) => {
			folga = Math.max(folga, node.getBoundingClientRect().bottom - caixa.top + 12);
		});
		return folga;
	}

	function ligarInteracoes() {
		if (el.viewport.dataset.interacoes === "1") {
			return;
		}
		el.viewport.dataset.interacoes = "1";

		const ponteiros = new Map();
		let arrastando = false;
		let inicio = { x: 0, y: 0, vx: 0, vy: 0 };
		let pinca = null;
		// Toque no card: o viewport captura o ponteiro e dá preventDefault no
		// pointerdown, então o evento `click` não chega no card de forma confiável.
		// Guardamos de onde o gesto partiu e decidimos no pointerup.
		let cardDoGesto = null;
		const TOLERANCIA_DO_TOQUE = 5;

		el.viewport.addEventListener("pointerdown", (evento) => {
			// A barra de controles vive dentro do viewport: sem esta saída, o
			// preventDefault abaixo engoliria o clique dos botões.
			if (evento.target.closest(".org-card__toggle, .organograma-controles")) {
				return;
			}
			// Impede que o navegador comece a arrastar uma seleção de texto por baixo
			// do pan. O CSS já bloqueia a seleção; isto cobre o resíduo que sobra de
			// um arrasto anterior e devolve o foco para o teclado continuar valendo.
			evento.preventDefault();
			// Foca para as setas continuarem panejando depois do arrasto, mas marca
			// que veio do ponteiro para o CSS não desenhar o anel de foco.
			el.viewport.dataset.foco = "ponteiro";
			el.viewport.focus({ preventScroll: true });
			const selecao = window.getSelection();
			if (selecao && !selecao.isCollapsed) {
				selecao.removeAllRanges();
			}

			ponteiros.set(evento.pointerId, { x: evento.clientX, y: evento.clientY });
			el.viewport.setPointerCapture(evento.pointerId);

			const card = evento.target.closest(".org-card:not(.org-card--grupo)");
			cardDoGesto = ponteiros.size === 1 && card ? card : null;

			if (ponteiros.size === 1) {
				arrastando = true;
				inicio = { x: evento.clientX, y: evento.clientY, vx: vista.x, vy: vista.y };
				el.viewport.classList.add("is-dragging");
			} else if (ponteiros.size === 2) {
				arrastando = false;
				pinca = { distancia: distanciaEntre(ponteiros), escala: vista.escala };
			}
		});

		el.viewport.addEventListener("pointermove", (evento) => {
			if (!ponteiros.has(evento.pointerId)) {
				return;
			}
			ponteiros.set(evento.pointerId, { x: evento.clientX, y: evento.clientY });

			if (pinca && ponteiros.size === 2) {
				const distancia = distanciaEntre(ponteiros);
				if (pinca.distancia > 0) {
					const centro = centroEntre(ponteiros);
					definirEscala(
						pinca.escala * (distancia / pinca.distancia),
						centro.x,
						centro.y
					);
				}
				return;
			}

			if (arrastando) {
				vista.x = inicio.vx + (evento.clientX - inicio.x);
				vista.y = inicio.vy + (evento.clientY - inicio.y);
				aplicarTransform();
			}
		});

		el.viewport.addEventListener("pointerup", (evento) => {
			const andou =
				Math.hypot(evento.clientX - inicio.x, evento.clientY - inicio.y) >
				TOLERANCIA_DO_TOQUE;
			if (cardDoGesto && !andou && ponteiros.size === 1) {
				alternarDetalhe(cardDoGesto.dataset.associado);
			}
			cardDoGesto = null;
		});

		["pointerup", "pointercancel", "pointerleave"].forEach((tipo) => {
			el.viewport.addEventListener(tipo, (evento) => {
				ponteiros.delete(evento.pointerId);
				if (ponteiros.size < 2) {
					pinca = null;
				}
				if (!ponteiros.size) {
					arrastando = false;
					el.viewport.classList.remove("is-dragging");
				}
			});
		});

		el.viewport.addEventListener(
			"wheel",
			(evento) => {
				if (evento.target.closest(".organograma-controles")) {
					return;
				}
				evento.preventDefault();
				const direcao = evento.deltaY > 0 ? -1 : 1;
				definirEscala(vista.escala + direcao * ZOOM_PASSO, evento.clientX, evento.clientY);
			},
			{ passive: false }
		);

		el.viewport.addEventListener("keydown", (evento) => {
			// Passou a navegar pelo teclado: o anel de foco volta a fazer falta.
			delete el.viewport.dataset.foco;

			if (evento.key === "Enter" || evento.key === " ") {
				const card = evento.target.closest?.(".org-card:not(.org-card--grupo)");
				if (card) {
					evento.preventDefault();
					alternarDetalhe(card.dataset.associado);
					return;
				}
			}

			const passo = evento.shiftKey ? 120 : 40;
			const movimentos = {
				ArrowUp: [0, passo],
				ArrowDown: [0, -passo],
				ArrowLeft: [passo, 0],
				ArrowRight: [-passo, 0],
			};
			const movimento = movimentos[evento.key];
			if (!movimento) {
				return;
			}
			evento.preventDefault();
			vista.x += movimento[0];
			vista.y += movimento[1];
			aplicarTransform();
		});

		el.viewport.addEventListener("blur", () => {
			delete el.viewport.dataset.foco;
		});

		el.menos?.addEventListener("click", () => definirEscala(vista.escala - ZOOM_PASSO));
		el.mais?.addEventListener("click", () => definirEscala(vista.escala + ZOOM_PASSO));
		el.ajustar?.addEventListener("click", ajustarATela);
		el.expandir?.addEventListener("click", () => {
			tudoExpandido = !tudoExpandido;
			el.canvas
				.querySelectorAll(".org-card__toggle")
				.forEach((botao) => alternar(botao, !tudoExpandido, false));
			ajustarATela();
			atualizarRotuloExpandir();
		});
	}

	function atualizarRotuloExpandir() {
		if (!el.expandir) {
			return;
		}
		const rotulo = tudoExpandido ? "Retrair tudo" : "Expandir tudo";
		el.expandir.setAttribute("aria-label", rotulo);
		const texto = el.expandir.querySelector(".organograma-acao-texto");
		if (texto) {
			texto.textContent = rotulo;
		}
	}

	function distanciaEntre(ponteiros) {
		const [a, b] = [...ponteiros.values()];
		return Math.hypot(a.x - b.x, a.y - b.y);
	}

	function centroEntre(ponteiros) {
		const [a, b] = [...ponteiros.values()];
		return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
	}

	function escapeHtml(valor) {
		return String(valor ?? "").replace(
			/[&<>"']/g,
			(caractere) =>
				({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[
					caractere
				])
		);
	}
});
