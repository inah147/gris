/**
 * Busca global do Portal (spec: docs/specs/busca-global/spec.md).
 *
 * Páginas e ações filtram no navegador a cada tecla; registros (pessoas, projetos,
 * festas, documentos) vêm de `gris.api.busca_global.buscar`, com debounce. O markup está
 * em templates/includes/portal_busca.html e o índice de páginas chega embutido nele.
 *
 * Usa `fetch` em vez de `frappe.call`: o do portal (website.js) nunca chama `error`, e a
 * falha da busca precisa aparecer para a pessoa.
 */
(function () {
	"use strict";

	const METODO = "gris.api.busca_global.buscar";
	const DEBOUNCE_MS = 200;
	const MIN_CARACTERES = 2;
	const LIMITE_PAGINAS = 8;
	const SPRITE = "/assets/gris/design_system/icons/lucide/sprite.svg";
	const SVG_NS = "http://www.w3.org/2000/svg";

	const normalizar = (texto) =>
		String(texto ?? "")
			.normalize("NFD")
			.replace(/[̀-ͯ]/g, "")
			.toLowerCase()
			.trim();

	// Terminações de singular/plural, as mesmas de `_TERMINACOES` em busca_global.py:
	// "contribuicao" precisa achar "Contribuições", e "mensal", "Mensais".
	const TERMINACOES = [
		["oes", ""],
		["aes", ""],
		["ao", ""],
		["ais", "a"],
		["al", "a"],
		["eis", "e"],
		["el", "e"],
		["s", ""],
	];

	// O radical é sempre prefixo da palavra: casar por ele só amplia o resultado.
	function radical(palavra) {
		if (palavra.length < 5) return palavra;
		const regra = TERMINACOES.find(([terminacao]) => palavra.endsWith(terminacao));
		if (!regra) return palavra;
		const candidato = palavra.slice(0, -regra[0].length) + regra[1];
		return candidato.length >= 4 ? candidato : palavra;
	}

	const palavrasDe = (termo) => termo.split(/\s+/).filter(Boolean).map(radical);

	// Mesma ordem do servidor (`_pontuacao`): título igual, começa com o termo, alguma
	// palavra começa com a primeira palavra do termo, contém. Menor é melhor.
	function pontuar(tituloNormalizado, termo, primeiraPalavra) {
		if (tituloNormalizado === termo) return 0;
		if (tituloNormalizado.startsWith(termo)) return 1;
		if (tituloNormalizado.split(/\s+/).some((parte) => parte.startsWith(primeiraPalavra)))
			return 2;
		return 3;
	}

	// Só caminho relativo do próprio portal vira link.
	const urlSegura = (url) =>
		typeof url === "string" && url.startsWith("/") && !url.startsWith("//");

	function icone(nome) {
		const svg = document.createElementNS(SVG_NS, "svg");
		svg.setAttribute("class", "ds-lucide ds-lucide--sm");
		svg.setAttribute("aria-hidden", "true");
		svg.setAttribute("focusable", "false");
		svg.setAttribute("viewBox", "0 0 24 24");
		const use = document.createElementNS(SVG_NS, "use");
		use.setAttribute("href", `${SPRITE}#${nome || "arrow-right"}`);
		svg.appendChild(use);
		return svg;
	}

	function lerPaginas() {
		const fonte = document.getElementById("portal-busca-paginas");
		let paginas = [];
		try {
			paginas = JSON.parse((fonte && fonte.textContent) || "[]");
		} catch (erro) {
			paginas = [];
		}
		return (Array.isArray(paginas) ? paginas : []).map((pagina) => ({
			...pagina,
			tituloNormalizado: normalizar(pagina.titulo),
			chave: normalizar(`${pagina.titulo} ${pagina.grupo || ""} ${pagina.termos || ""}`),
		}));
	}

	function acoesDisponiveis() {
		const escuro = document.documentElement.classList.contains("dark");
		return [
			{
				titulo: escuro ? "Usar tema claro" : "Usar tema escuro",
				icone: escuro ? "sun" : "moon",
				acao: "toggle-theme",
				chave: normalizar("tema claro escuro modo noturno aparência cores dark light"),
			},
			{
				titulo: "Desconectar",
				icone: "log-out",
				acao: "logout",
				chave: normalizar("desconectar sair logout encerrar sessão"),
			},
		];
	}

	function iniciar() {
		const dialog = document.getElementById("portal-busca");
		const input = document.getElementById("portal-busca-input");
		const menu = document.getElementById("portal-busca-resultados");
		if (!dialog || !input || !menu) return;

		const vazio = dialog.querySelector("[data-portal-busca-vazio]");
		const erro = dialog.querySelector("[data-portal-busca-erro]");
		const carregando = dialog.querySelector("[data-portal-busca-carregando]");
		const atalho = document.querySelector("[data-portal-busca-atalho]");

		const estado = {
			paginas: lerPaginas(),
			// Última resposta do servidor: { grupos: [...] }.
			registros: null,
			carregando: false,
			itens: [],
			ativo: -1,
			// URL ou ação do item destacado, para mantê-lo quando a lista é redesenhada.
			chaveAtiva: null,
			timer: null,
			controller: null,
			seq: 0,
		};

		if (
			atalho &&
			/mac|iphone|ipad/i.test(navigator.userAgentData?.platform || navigator.platform || "")
		) {
			atalho.textContent = "⌘ K";
		}

		// ---------------------------------------------------------------- filtro local

		function filtrarPaginas(termo) {
			if (!termo) return estado.paginas.filter((pagina) => pagina.modulo);
			const palavras = palavrasDe(termo);
			return estado.paginas
				.filter((pagina) => palavras.every((palavra) => pagina.chave.includes(palavra)))
				.map((pagina) => ({
					pagina,
					nota: pontuar(pagina.tituloNormalizado, termo, palavras[0]),
				}))
				.sort(
					(a, b) =>
						a.nota - b.nota ||
						a.pagina.tituloNormalizado.localeCompare(b.pagina.tituloNormalizado)
				)
				.slice(0, LIMITE_PAGINAS)
				.map(({ pagina }) => pagina);
		}

		function filtrarAcoes(termo) {
			const palavras = palavrasDe(termo);
			return acoesDisponiveis().filter((acao) => {
				const chave = `${normalizar(acao.titulo)} ${acao.chave}`;
				return palavras.every((palavra) => chave.includes(palavra));
			});
		}

		function montarGrupos() {
			const termo = normalizar(input.value);
			const grupos = [];

			const paginas = filtrarPaginas(termo);
			if (paginas.length) {
				grupos.push({
					chave: "paginas",
					rotulo: "Páginas",
					itens: paginas.map((pagina) => ({
						tipo: "pagina",
						titulo: pagina.titulo,
						subtitulo: pagina.grupo || "",
						url: pagina.url,
						icone: pagina.icone,
					})),
				});
			}

			if (termo.length >= MIN_CARACTERES && estado.registros) {
				estado.registros.grupos.forEach((grupo) => {
					const itens = (grupo.itens || []).filter((item) => urlSegura(item.url));
					if (!itens.length) return;
					grupos.push({
						chave: grupo.chave,
						rotulo: grupo.rotulo,
						itens: itens.map((item) => ({
							...item,
							tipo: "registro",
							icone: grupo.icone,
						})),
					});
				});
			}

			const acoes = filtrarAcoes(termo);
			if (acoes.length) {
				grupos.push({
					chave: "acoes",
					rotulo: "Ações",
					itens: acoes.map((acao) => ({ ...acao, tipo: "acao" })),
				});
			}
			return grupos;
		}

		// ---------------------------------------------------------------- desenho

		function criarItem(item, indice) {
			const el = document.createElement(item.url ? "a" : "div");
			el.id = `portal-busca-item-${indice}`;
			el.setAttribute("role", "menuitem");
			el.tabIndex = -1;
			el.dataset.tipo = item.tipo;
			if (item.url) el.setAttribute("href", item.url);
			// O shell (web_sidebar_base.html) já trata estes `data-action` no clique.
			if (item.acao) el.dataset.action = item.acao;

			const texto = document.createElement("span");
			texto.className = "portal-busca__item-texto";
			const titulo = document.createElement("span");
			titulo.className = "portal-busca__item-titulo";
			titulo.textContent = item.titulo || "";
			texto.appendChild(titulo);
			if (item.subtitulo) {
				const meta = document.createElement("span");
				meta.className = "portal-busca__item-meta";
				meta.textContent = item.subtitulo;
				texto.appendChild(meta);
			}

			el.append(icone(item.icone), texto);
			return el;
		}

		function renderizar({ manterAtivo = false } = {}) {
			const grupos = montarGrupos();
			const chaveAnterior = manterAtivo ? estado.chaveAtiva : null;

			menu.replaceChildren();
			estado.itens = [];
			grupos.forEach((grupo) => {
				const bloco = document.createElement("div");
				bloco.setAttribute("role", "group");
				bloco.dataset.grupo = grupo.chave;
				const rotulo = document.createElement("span");
				rotulo.setAttribute("role", "heading");
				rotulo.id = `portal-busca-grupo-${grupo.chave}`;
				rotulo.textContent = grupo.rotulo;
				bloco.setAttribute("aria-labelledby", rotulo.id);
				bloco.appendChild(rotulo);

				grupo.itens.forEach((item) => {
					const el = criarItem(item, estado.itens.length);
					estado.itens.push({ el, item });
					bloco.appendChild(el);
				});
				menu.appendChild(bloco);
			});

			const temItens = estado.itens.length > 0;
			// Sem itens o menu some: senão o Basecoat escreve "No results found" no ::before.
			menu.hidden = !temItens;
			const termo = normalizar(input.value);
			if (vazio) vazio.hidden = temItens || !termo || estado.carregando;

			const indice = chaveAnterior
				? estado.itens.findIndex(({ item }) => chaveDe(item) === chaveAnterior)
				: -1;
			destacar(indice >= 0 ? indice : temItens ? 0 : -1);
		}

		const chaveDe = (item) => item.url || `acao:${item.acao}`;

		function destacar(indice, { rolar = true } = {}) {
			estado.itens.forEach(({ el }, i) => el.classList.toggle("active", i === indice));
			estado.ativo = indice;
			const atual = estado.itens[indice];
			if (!atual) {
				estado.chaveAtiva = null;
				input.removeAttribute("aria-activedescendant");
				return;
			}
			estado.chaveAtiva = chaveDe(atual.item);
			input.setAttribute("aria-activedescendant", atual.el.id);
			if (rolar) atual.el.scrollIntoView({ block: "nearest" });
		}

		function mover(passo) {
			const total = estado.itens.length;
			if (!total) return;
			const proximo = estado.ativo < 0 ? 0 : (estado.ativo + passo + total) % total;
			destacar(proximo);
		}

		// ---------------------------------------------------------------- busca remota

		function definirCarregando(ativo) {
			estado.carregando = ativo;
			if (carregando) carregando.hidden = !ativo;
			menu.setAttribute("aria-busy", ativo ? "true" : "false");
		}

		function cancelarBusca() {
			clearTimeout(estado.timer);
			if (estado.controller) estado.controller.abort();
			estado.controller = null;
			// Invalida qualquer resposta ainda a caminho.
			estado.seq += 1;
			definirCarregando(false);
		}

		function agendarBusca() {
			cancelarBusca();
			const termo = input.value.trim();
			if (normalizar(termo).length < MIN_CARACTERES) {
				estado.registros = null;
				if (erro) erro.hidden = true;
				return;
			}
			definirCarregando(true);
			estado.timer = setTimeout(() => buscarRegistros(termo), DEBOUNCE_MS);
		}

		async function buscarRegistros(termo) {
			const controller = new AbortController();
			estado.controller = controller;
			const seq = estado.seq;
			try {
				const resposta = await fetch(
					`/api/method/${METODO}?${new URLSearchParams({ termo })}`,
					{
						credentials: "same-origin",
						headers: { Accept: "application/json" },
						signal: controller.signal,
					}
				);
				if (!resposta.ok) throw new Error(`HTTP ${resposta.status}`);
				const corpo = await resposta.json();
				if (seq !== estado.seq) return;
				const dados =
					corpo && corpo.message && corpo.message.ok ? corpo.message.data : null;
				if (!dados) throw new Error("Resposta sem dados");
				estado.registros = { grupos: Array.isArray(dados.grupos) ? dados.grupos : [] };
				if (erro) erro.hidden = true;
			} catch (falha) {
				if (falha.name === "AbortError" || seq !== estado.seq) return;
				estado.registros = null;
				if (erro) erro.hidden = false;
			} finally {
				if (seq === estado.seq) {
					definirCarregando(false);
					renderizar({ manterAtivo: true });
				}
			}
		}

		// ---------------------------------------------------------------- abrir/fechar

		function abrir() {
			if (dialog.open) return;
			input.value = "";
			estado.registros = null;
			if (erro) erro.hidden = true;
			renderizar();
			dialog.showModal();
			input.focus();
		}

		function fechar() {
			if (dialog.open) dialog.close();
		}

		function abrirDestacado(novaAba) {
			const atual = estado.itens[estado.ativo];
			if (!atual) return;
			if (atual.item.url) {
				if (novaAba) {
					window.open(atual.item.url, "_blank", "noopener");
					return;
				}
				fechar();
				window.location.assign(atual.item.url);
				return;
			}
			// Ação: o clique cai no tratamento do shell e no `click` do menu, que fecha.
			atual.el.click();
		}

		dialog.addEventListener("close", cancelarBusca);

		// Clique no fundo escurecido: o alvo é o próprio <dialog>, não o painel.
		dialog.addEventListener("click", (event) => {
			if (event.target === dialog) fechar();
		});

		dialog.querySelector("[data-portal-busca-fechar]")?.addEventListener("click", fechar);

		input.addEventListener("input", () => {
			renderizar();
			agendarBusca();
		});

		input.addEventListener("keydown", (event) => {
			if (event.isComposing) return;
			switch (event.key) {
				case "ArrowDown":
					event.preventDefault();
					mover(1);
					break;
				case "ArrowUp":
					event.preventDefault();
					mover(-1);
					break;
				case "Home":
					if (!estado.itens.length) return;
					event.preventDefault();
					destacar(0);
					break;
				case "End":
					if (!estado.itens.length) return;
					event.preventDefault();
					destacar(estado.itens.length - 1);
					break;
				case "Enter":
					event.preventDefault();
					abrirDestacado(event.ctrlKey || event.metaKey);
					break;
				default:
			}
		});

		menu.addEventListener("mousemove", (event) => {
			const el = event.target.closest('[role="menuitem"]');
			if (!el) return;
			const indice = estado.itens.findIndex((registro) => registro.el === el);
			if (indice !== -1 && indice !== estado.ativo) destacar(indice, { rolar: false });
		});

		menu.addEventListener("click", (event) => {
			const el = event.target.closest('[role="menuitem"]');
			if (!el) return;
			const novaAba = event.ctrlKey || event.metaKey || event.shiftKey;
			if (el.dataset.action || !novaAba) fechar();
		});

		document.querySelectorAll("[data-portal-busca-abrir]").forEach((gatilho) => {
			gatilho.addEventListener("click", abrir);
		});

		const campoEditavel = (alvo) =>
			alvo instanceof Element &&
			(alvo.isContentEditable ||
				Boolean(alvo.closest("input, textarea, select, [contenteditable]")));

		// Outro modal aberto (formulário da página): o atalho não empilha a busca por cima.
		const outroModalAberto = () =>
			Boolean(document.querySelector("dialog[open]:not(#portal-busca)"));

		document.addEventListener("keydown", (event) => {
			const atalhoK =
				(event.key === "k" || event.key === "K") &&
				(event.ctrlKey || event.metaKey) &&
				!event.altKey &&
				!event.shiftKey;
			if (atalhoK) {
				if (dialog.open) {
					event.preventDefault();
					fechar();
				} else if (!outroModalAberto()) {
					event.preventDefault();
					abrir();
				}
				return;
			}
			if (
				event.key === "/" &&
				!dialog.open &&
				!event.ctrlKey &&
				!event.metaKey &&
				!event.altKey &&
				!campoEditavel(event.target) &&
				!outroModalAberto()
			) {
				event.preventDefault();
				abrir();
			}
		});
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", iniciar);
	} else {
		iniciar();
	}
})();
