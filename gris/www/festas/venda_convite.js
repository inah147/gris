(function () {
	"use strict";

	const data = window._vendaConvite || { festas: [], portal_logo: "" };

	// ─── Estado ──────────────────────────────────────────────────────────────

	let festaSelecionada = null;
	let festaInfo = null;
	let opcoes = [];
	const carrinho = new Map(); // opcao_name -> quantidade
	let doarFlag = false;
	let doacaoValor = 10;
	let pagador = { nome: "", email: "", telefone: "" };
	let pagadorRecebe = false;
	let convidados = []; // [{nome, email, telefone, tipo_convite}]
	let convidadoIdx = 0;
	let pedidoNome = null;
	let linkPagamento = "";
	let pollTimer = null;
	let pollTries = 0;
	let ultimoResumo = null;

	const TABS = ["escolha", "pedido", "convidados", "revisao"];

	// ─── Helpers ─────────────────────────────────────────────────────────────

	function toast(message, category) {
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: { config: { category: category || "info", description: message, duration: 3500 } },
			})
		);
	}

	function fmtMoeda(valor) {
		return new Intl.NumberFormat("pt-BR", {
			style: "currency", currency: "BRL", minimumFractionDigits: 2,
		}).format(Number(valor) || 0);
	}

	function api(method, args) {
		return new Promise(function (resolve, reject) {
			frappe.call({
				method: method,
				args: args,
				callback: function (r) {
					if (r && r.message) resolve(r.message);
					else reject(new Error("Resposta inesperada."));
				},
				error: function (err) {
					const msg = (err && err._server_messages) || err.message || "Erro de servidor.";
					reject(new Error(typeof msg === "string" ? msg : "Erro de servidor."));
				},
			});
		});
	}

	function escapeHtml(text) {
		const div = document.createElement("div");
		div.textContent = String(text == null ? "" : text);
		return div.innerHTML;
	}

	function totalConvitesNoCarrinho() {
		let total = 0;
		carrinho.forEach(function (q) { total += Number(q || 0); });
		return total;
	}

	function carrinhoComoArray() {
		const arr = [];
		carrinho.forEach(function (q, opcao) {
			if (q > 0) arr.push({ opcao_convite: opcao, quantidade: q });
		});
		return arr;
	}

	// ─── Navegação de tabs ──────────────────────────────────────────────────

	function tabTrigger(id) {
		const idx = TABS.indexOf(id);
		if (idx < 0) return null;
		return document.getElementById("vc-tabs-tab-" + (idx + 1));
	}

	function activateTab(id) {
		const trigger = tabTrigger(id);
		if (trigger) trigger.click();
	}

	function bloquearAbas() {
		// Abas só navegáveis pelos botões internos: bloqueia clique direto e foco
		// por teclado, mas permite ativação programática via .click().
		document.querySelectorAll('#vc-tabs [role="tab"]').forEach(function (tab) {
			tab.setAttribute("aria-disabled", "true");
			tab.setAttribute("tabindex", "-1");
			tab.style.pointerEvents = "none";
			tab.style.cursor = "default";
		});
	}

	// ─── Festa: seleção ─────────────────────────────────────────────────────

	function refreshTituloFesta() {
		const titleEl = document.getElementById("vc-festa-title");
		const subEl = document.getElementById("vc-festa-subtitle");
		if (!festaInfo) {
			if (titleEl) titleEl.textContent = "Comprar convites";
			if (subEl) subEl.textContent = "Selecione a festa para começar.";
			return;
		}
		if (titleEl) titleEl.textContent = festaInfo.nome_festa || "Comprar convites";
		if (subEl) {
			if (festaInfo.data) {
				const parts = festaInfo.data.split("-");
				const dataLabel = parts.length === 3 ? parts[2] + "/" + parts[1] + "/" + parts[0] : festaInfo.data;
				subEl.textContent = "Festa em " + dataLabel + ".";
			} else {
				subEl.textContent = "";
			}
		}
	}

	function carregarFesta(festaName) {
		if (!festaName) return Promise.resolve();
		return api("gris.api.festas.venda_convite.listar_opcoes", { festa_name: festaName })
			.then(function (resp) {
				festaSelecionada = festaName;
				festaInfo = resp.festa;
				opcoes = resp.opcoes || [];
				carrinho.clear();
				doarFlag = false;
				doacaoValor = 10;
				convidados = [];
				convidadoIdx = 0;
				pedidoNome = null;
				linkPagamento = "";
				ultimoResumo = null;
				stopPolling();

				const wrapper = document.getElementById("vc-tabs-wrapper");
				if (wrapper) wrapper.hidden = false;
				refreshTituloFesta();
				renderVitrine();
				renderPedido();
				updateDoacaoVisibility();
				bloquearAbas();
				activateTab("escolha");
			})
			.catch(function (err) {
				toast(err.message || "Não foi possível carregar a festa.", "error");
			});
	}

	function trocarFestaConfirm(novaFesta) {
		if (festaSelecionada && totalConvitesNoCarrinho() > 0) {
			if (!window.confirm("Trocar de festa vai apagar o carrinho atual. Continuar?")) {
				return Promise.resolve(false);
			}
		}
		return carregarFesta(novaFesta).then(function () { return true; });
	}

	// ─── Vitrine ────────────────────────────────────────────────────────────

	function getQty(opcaoName) {
		return Number(carrinho.get(opcaoName) || 0);
	}

	function setQty(opcaoName, valor) {
		const v = Math.max(0, Math.floor(Number(valor) || 0));
		if (v <= 0) carrinho.delete(opcaoName);
		else carrinho.set(opcaoName, v);
		atualizarBotaoIrParaPedido();
	}

	function atualizarBotaoIrParaPedido() {
		const btn = document.getElementById("btn-escolha-revisar");
		if (!btn) return;
		btn.disabled = totalConvitesNoCarrinho() <= 0;
	}

	function renderCardConvite(opcao) {
		const qtd = getQty(opcao.name);
		const imagem = opcao.imagem_capa
			? '<img class="vc-card-convite__imagem" src="' + escapeHtml(opcao.imagem_capa) + '" alt="' + escapeHtml(opcao.nome_convite) + '" />'
			: '<div class="vc-card-convite__imagem vc-card-convite__imagem--placeholder" aria-hidden="true">' +
			  '<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M2 9a4 4 0 0 1 4-4h12a4 4 0 0 1 4 4 2 2 0 0 0-2 2v2a2 2 0 0 0 2 2 4 4 0 0 1-4 4H6a4 4 0 0 1-4-4 2 2 0 0 0 2-2v-2a2 2 0 0 0-2-2Z"/></svg>' +
			  "</div>";
		return '<article class="vc-card-convite" data-vc-opcao="' + escapeHtml(opcao.name) + '">' +
			imagem +
			'<div class="vc-card-convite__body">' +
			'<h3 class="vc-card-convite__title">' + escapeHtml(opcao.nome_convite) + "</h3>" +
			'<p class="vc-card-convite__price">' + fmtMoeda(opcao.valor) + "</p>" +
			'<div class="vc-qty">' +
			'<button type="button" class="btn-sm-outline" data-vc-decr="' + escapeHtml(opcao.name) + '" aria-label="Diminuir">−</button>' +
			'<input type="number" min="0" step="1" value="' + qtd + '" class="vc-qty__input" data-vc-qty="' + escapeHtml(opcao.name) + '" inputmode="numeric" />' +
			'<button type="button" class="btn-sm-outline" data-vc-incr="' + escapeHtml(opcao.name) + '" aria-label="Aumentar">+</button>' +
			"</div>" +
			"</div></article>";
	}

	function bindCardHandlers(cardEl) {
		const opcaoName = cardEl.getAttribute("data-vc-opcao");
		const input = cardEl.querySelector('[data-vc-qty]');
		const decr = cardEl.querySelector('[data-vc-decr]');
		const incr = cardEl.querySelector('[data-vc-incr]');

		function aplicar(valor) {
			setQty(opcaoName, valor);
			if (input) input.value = String(getQty(opcaoName));
		}

		if (incr) incr.addEventListener("click", function () { aplicar(getQty(opcaoName) + 1); });
		if (decr) decr.addEventListener("click", function () { aplicar(getQty(opcaoName) - 1); });
		if (input) {
			input.addEventListener("input", function () {
				setQty(opcaoName, input.value);
			});
			input.addEventListener("change", function () {
				aplicar(input.value);
			});
		}
	}

	function renderVitrine() {
		const container = document.getElementById("vc-vitrine");
		if (!container) return;
		if (!opcoes.length) {
			container.innerHTML = '<p class="text-sm text-muted-foreground">Nenhuma opção disponível.</p>';
			atualizarBotaoIrParaPedido();
			return;
		}
		container.innerHTML = opcoes.map(renderCardConvite).join("");
		container.querySelectorAll(".vc-card-convite").forEach(bindCardHandlers);
		atualizarBotaoIrParaPedido();
	}

	// ─── Aba Pedido ─────────────────────────────────────────────────────────

	function updateDoacaoVisibility() {
		const section = document.getElementById("vc-doacao-section");
		if (!section) return;
		section.hidden = !(festaInfo && festaInfo.aceitar_doacoes);
	}

	function renderPedidoTabela(resumo) {
		const tbody = document.getElementById("vc-pedido-tabela-body");
		if (!tbody) return;
		const linhas = [];
		(resumo.itens || []).forEach(function (it) {
			linhas.push(
				"<tr>" +
				"<td>" + escapeHtml(it.nome_convite) + "</td>" +
				"<td>" + escapeHtml(String(it.quantidade)) + "</td>" +
				'<td class="vc-col-num">' + fmtMoeda(it.subtotal) + "</td>" +
				"</tr>"
			);
		});
		linhas.push(
			'<tr class="vc-tabela-subtotal" data-vc-row="subtotal">' +
			'<td colspan="2">Subtotal de convites</td>' +
			'<td class="vc-col-num">' + fmtMoeda(resumo.subtotal_convites) + "</td>" +
			"</tr>"
		);
		if (resumo.valor_doacao > 0) {
			linhas.push(
				'<tr data-vc-row="doacao">' +
				'<td colspan="2">Doação</td>' +
				'<td class="vc-col-num">' + fmtMoeda(resumo.valor_doacao) + "</td>" +
				"</tr>"
			);
		}
		linhas.push(
			'<tr class="vc-tabela-total" data-vc-row="total">' +
			'<td colspan="2"><strong>Total</strong></td>' +
			'<td class="vc-col-num"><strong>' + fmtMoeda(resumo.total) + "</strong></td>" +
			"</tr>"
		);
		tbody.innerHTML = linhas.join("");
	}

	function atualizarLinhasDoacao() {
		if (!ultimoResumo) return;
		const valor = doarFlag ? doacaoValor : 0;
		ultimoResumo.valor_doacao = valor;
		ultimoResumo.total = Number(ultimoResumo.subtotal_convites || 0) + valor;

		const tbody = document.getElementById("vc-pedido-tabela-body");
		if (!tbody) return;
		const linhaDoacao = tbody.querySelector('[data-vc-row="doacao"]');
		const linhaTotal = tbody.querySelector('[data-vc-row="total"]');
		if (valor > 0) {
			const html =
				'<td colspan="2">Doação</td>' +
				'<td class="vc-col-num">' + fmtMoeda(valor) + "</td>";
			if (linhaDoacao) {
				linhaDoacao.innerHTML = html;
			} else if (linhaTotal) {
				const tr = document.createElement("tr");
				tr.setAttribute("data-vc-row", "doacao");
				tr.innerHTML = html;
				tbody.insertBefore(tr, linhaTotal);
			}
		} else if (linhaDoacao) {
			linhaDoacao.remove();
		}
		if (linhaTotal) {
			linhaTotal.innerHTML =
				'<td colspan="2"><strong>Total</strong></td>' +
				'<td class="vc-col-num"><strong>' + fmtMoeda(ultimoResumo.total) + "</strong></td>";
		}
	}

	function renderPedido() {
		const tbody = document.getElementById("vc-pedido-tabela-body");
		if (!tbody) return;
		const itens = carrinhoComoArray();
		if (!itens.length) {
			tbody.innerHTML = '<tr><td colspan="3" class="text-sm text-muted-foreground">Adicione convites para ver o resumo.</td></tr>';
			ultimoResumo = null;
			const btn = document.getElementById("btn-pedido-continuar");
			if (btn) btn.disabled = true;
			return;
		}
		api("gris.api.festas.venda_convite.get_resumo_carrinho", {
			festa_name: festaSelecionada,
			itens: JSON.stringify(itens),
			doacao_valor: doarFlag ? doacaoValor : 0,
		}).then(function (resumo) {
			ultimoResumo = resumo;
			renderPedidoTabela(resumo);
			atualizarBotaoContinuarPedido();
		}).catch(function (err) {
			tbody.innerHTML = '<tr><td colspan="3" class="text-sm text-destructive">' + escapeHtml(err.message || "Erro ao calcular pedido.") + "</td></tr>";
			atualizarBotaoContinuarPedido();
		});
	}

	const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

	function emailValido(valor) {
		return EMAIL_RE.test(String(valor || "").trim());
	}

	function lerTelefoneDOM() {
		const telWrap = document.getElementById("vc-pagador-telefone");
		if (!telWrap) return "";
		const hidden = telWrap.querySelector("[data-phone-input-value]");
		if (hidden && hidden.value) return hidden.value.trim();
		// Fallback: basecoat pode não ter inicializado — usa o input visível
		const num = telWrap.querySelector("[data-phone-input-number]");
		const raw = num ? num.value.replace(/\D/g, "") : "";
		return raw;
	}

	function lerPagadorDOM() {
		const nomeEl = document.getElementById("vc-pagador-nome");
		const emailEl = document.getElementById("vc-pagador-email");
		return {
			nome: (nomeEl ? nomeEl.value : "").trim(),
			email: (emailEl ? emailEl.value : "").trim(),
			telefone: lerTelefoneDOM(),
		};
	}

	function sincronizarPagador() {
		Object.assign(pagador, lerPagadorDOM());
	}

	function pagadorValido() {
		const p = lerPagadorDOM();
		return !!(p.nome && emailValido(p.email) && p.telefone);
	}

	function atualizarBotaoContinuarPedido() {
		sincronizarPagador();
		const btn = document.getElementById("btn-pedido-continuar");
		if (!btn) return;
		btn.disabled = !(totalConvitesNoCarrinho() > 0 && pagadorValido());
	}

	function initPedidoControls() {
		// Pagador — nome. `change` cobre autofill do navegador (Safari/Chrome
		// nem sempre disparam `input` em autofill ou restauração de sessão).
		const nomeEl = document.getElementById("vc-pagador-nome");
		if (nomeEl) {
			const onNome = function () {
				pagador.nome = nomeEl.value.trim();
				atualizarBotaoContinuarPedido();
			};
			nomeEl.addEventListener("input", onNome);
			nomeEl.addEventListener("change", onNome);
		}

		// Pagador — e-mail com validação
		const emailEl = document.getElementById("vc-pagador-email");
		const emailErro = document.getElementById("vc-pagador-email-erro");
		function validarEmailUI() {
			if (!emailEl) return;
			const v = emailEl.value.trim();
			const ok = !v || emailValido(v);
			if (emailErro) emailErro.hidden = ok;
			emailEl.setAttribute("aria-invalid", ok ? "false" : "true");
		}
		if (emailEl) {
			const onEmail = function () {
				pagador.email = emailEl.value.trim();
				if (emailErro && !emailErro.hidden) validarEmailUI();
				atualizarBotaoContinuarPedido();
			};
			emailEl.addEventListener("input", onEmail);
			emailEl.addEventListener("change", onEmail);
			emailEl.addEventListener("blur", validarEmailUI);
		}

		// Pagador — telefone via phone-input do design system. Listeners redundantes
		// porque o basecoat pode inicializar tarde; sempre lemos o DOM em
		// atualizarBotaoContinuarPedido para garantir o estado correto.
		const telWrap = document.getElementById("vc-pagador-telefone");
		if (telWrap) {
			telWrap.addEventListener("phone-input:change", atualizarBotaoContinuarPedido);
			const hidden = telWrap.querySelector("[data-phone-input-value]");
			if (hidden) hidden.addEventListener("change", atualizarBotaoContinuarPedido);
			const numero = telWrap.querySelector("[data-phone-input-number]");
			if (numero) {
				numero.addEventListener("input", atualizarBotaoContinuarPedido);
				numero.addEventListener("change", atualizarBotaoContinuarPedido);
			}
		}

		// Doação — atualização local, sem refetch (evita pisca)
		document.querySelectorAll('input[name="vc-doar"]').forEach(function (r) {
			r.addEventListener("change", function () {
				doarFlag = r.value === "sim" && r.checked;
				const ctrl = document.getElementById("vc-doacao-controls");
				if (ctrl) ctrl.hidden = !doarFlag;
				atualizarLinhasDoacao();
			});
		});

		const doacaoBtns = document.querySelectorAll("[data-vc-doacao-valor]");
		doacaoBtns.forEach(function (btn) {
			btn.addEventListener("click", function () {
				const valor = Number(btn.getAttribute("data-vc-doacao-valor")) || 0;
				doacaoValor = valor;
				doacaoBtns.forEach(function (b) {
					const active = b === btn;
					b.classList.toggle("is-active", active);
					b.setAttribute("aria-pressed", active ? "true" : "false");
				});
				atualizarLinhasDoacao();
			});
		});
	}

	// ─── Aba Convidados ─────────────────────────────────────────────────────

	function expandirConvidados() {
		const total = totalConvitesNoCarrinho();
		const novos = [];
		const tiposExpandidos = [];
		carrinho.forEach(function (q, opcaoName) {
			const opcao = opcoes.find(function (o) { return o.name === opcaoName; });
			const label = opcao ? opcao.nome_convite : opcaoName;
			for (let i = 0; i < q; i += 1) tiposExpandidos.push(label);
		});
		for (let i = 0; i < total; i += 1) {
			const prev = convidados[i] || { nome: "", email: "", telefone: "" };
			novos.push({
				nome: prev.nome || "",
				email: prev.email || "",
				telefone: prev.telefone || "",
				tipo_convite: tiposExpandidos[i] || "",
			});
		}
		convidados = novos;
		if (convidadoIdx >= convidados.length) convidadoIdx = 0;
	}

	function renderConvidados() {
		expandirConvidados();
		const galeria = document.getElementById("vc-galeria");
		const nomesBox = document.getElementById("vc-nomes-pagador-recebe");
		const temConvidado = convidados.length > 0;
		if (galeria) galeria.hidden = pagadorRecebe || !temConvidado;
		if (nomesBox) nomesBox.hidden = !pagadorRecebe || !temConvidado;
		if (pagadorRecebe) {
			renderNomesPagadorRecebe();
		} else {
			renderGaleriaAtual();
		}
		atualizarBotaoConvidadosContinuar();
	}

	function renderNomesPagadorRecebe() {
		const lista = document.getElementById("vc-nomes-pagador-recebe-lista");
		const btnUsar = document.getElementById("vc-usar-dados-pagador");
		if (btnUsar) btnUsar.hidden = convidados.length !== 1;
		if (!lista) return;
		lista.innerHTML = convidados.map(function (c, idx) {
			const tipo = c.tipo_convite ? ' <span class="vc-nomes-pagador-recebe__tipo">· ' + escapeHtml(c.tipo_convite) + "</span>" : "";
			const valor = escapeHtml(c.nome || "");
			const inputId = "vc-pr-nome-" + idx;
			return '<div class="vc-nomes-pagador-recebe__item">'
				+ '<label class="vc-nomes-pagador-recebe__label" for="' + inputId + '">'
				+ "Convite " + (idx + 1) + tipo
				+ "</label>"
				+ '<input class="input" type="text" id="' + inputId + '" data-vc-pr-idx="' + idx + '"'
				+ ' value="' + valor + '" required autocomplete="name" placeholder="Nome do convidado">'
				+ "</div>";
		}).join("");
		const inputs = lista.querySelectorAll("input[data-vc-pr-idx]");
		inputs.forEach(function (inp) {
			inp.addEventListener("input", function () {
				const idx = parseInt(inp.getAttribute("data-vc-pr-idx"), 10);
				if (convidados[idx]) convidados[idx].nome = inp.value.trim();
				atualizarBotaoConvidadosContinuar();
			});
		});
	}

	function lerTelefoneConvidadoDOM() {
		const tel = document.getElementById("vc-convidado-telefone");
		if (!tel) return "";
		const hidden = tel.querySelector("[data-phone-input-value]");
		if (hidden && hidden.value) return hidden.value.trim();
		const num = tel.querySelector("[data-phone-input-number]");
		return num ? num.value.replace(/\D/g, "") : "";
	}

	function setarTelefoneConvidado(valor) {
		const tel = document.getElementById("vc-convidado-telefone");
		if (!tel) return;
		function aplicar() {
			try { tel.value = valor || ""; } catch (e) { /* setter ainda não definido */ }
		}
		if (tel.dataset.phoneInputInitialized === "true") {
			aplicar();
		} else {
			tel.addEventListener("basecoat:initialized", aplicar, { once: true });
		}
	}

	function renderGaleriaAtual() {
		if (!convidados.length) return;
		const indicator = document.getElementById("vc-galeria-indicator");
		const tipo = document.getElementById("vc-galeria-tipo");
		const nome = document.getElementById("vc-convidado-nome");
		const email = document.getElementById("vc-convidado-email");
		const emailErro = document.getElementById("vc-convidado-email-erro");
		const c = convidados[convidadoIdx] || {};
		if (indicator) indicator.textContent = "Convidado " + (convidadoIdx + 1) + "/" + convidados.length;
		if (tipo) tipo.textContent = c.tipo_convite ? "Convite: " + c.tipo_convite : "";
		if (nome) nome.value = c.nome || "";
		if (email) {
			email.value = c.email || "";
			email.setAttribute("aria-invalid", "false");
		}
		if (emailErro) emailErro.hidden = true;
		setarTelefoneConvidado(c.telefone || "");
	}

	function salvarConvidadoAtual() {
		if (!convidados.length) return;
		const c = convidados[convidadoIdx] || {};
		const nome = document.getElementById("vc-convidado-nome");
		const email = document.getElementById("vc-convidado-email");
		c.nome = (nome && nome.value || "").trim();
		c.email = (email && email.value || "").trim();
		c.telefone = lerTelefoneConvidadoDOM();
		convidados[convidadoIdx] = c;
	}

	function atualizarBotaoConvidadosContinuar() {
		const btn = document.getElementById("btn-convidados-continuar");
		if (!btn) return;
		if (pagadorRecebe) {
			const valido = convidados.length > 0 && convidados.every(function (c) {
				return c.nome && c.nome.trim().length > 0;
			});
			btn.disabled = !valido;
			return;
		}
		const valido = convidados.length > 0 && convidados.every(function (c) {
			return c.nome && emailValido(c.email);
		});
		btn.disabled = !valido;
	}

	function initConvidadosControls() {
		// O macro switch coloca o id no <label> externo; o checkbox real é o
		// <input> interno. Listener delegado no wrap captura o change que
		// borbulha do input (mais robusto que listener direto no input).
		const recebeWrap = document.getElementById("vc-pagador-recebe");
		const recebeInput = recebeWrap && recebeWrap.querySelector('input[type="checkbox"]');
		function onSwitchChange() {
			if (!recebeInput) return;
			pagadorRecebe = !!recebeInput.checked;
			renderConvidados();
		}
		if (recebeWrap) recebeWrap.addEventListener("change", onSwitchChange);
		if (recebeInput) recebeInput.addEventListener("change", onSwitchChange);
		const prev = document.getElementById("vc-galeria-prev");
		const next = document.getElementById("vc-galeria-next");
		if (prev) prev.addEventListener("click", function () {
			salvarConvidadoAtual();
			if (convidadoIdx > 0) convidadoIdx -= 1;
			renderGaleriaAtual();
		});
		if (next) next.addEventListener("click", function () {
			salvarConvidadoAtual();
			if (convidadoIdx < convidados.length - 1) convidadoIdx += 1;
			renderGaleriaAtual();
		});
		// Nome
		const nomeConvEl = document.getElementById("vc-convidado-nome");
		if (nomeConvEl) {
			nomeConvEl.addEventListener("input", function () {
				salvarConvidadoAtual();
				atualizarBotaoConvidadosContinuar();
			});
		}

		// E-mail com validação inline
		const emailConvEl = document.getElementById("vc-convidado-email");
		const emailConvErro = document.getElementById("vc-convidado-email-erro");
		function validarEmailConvidadoUI() {
			if (!emailConvEl) return;
			const v = emailConvEl.value.trim();
			const ok = !v || emailValido(v);
			if (emailConvErro) emailConvErro.hidden = ok;
			emailConvEl.setAttribute("aria-invalid", ok ? "false" : "true");
		}
		if (emailConvEl) {
			emailConvEl.addEventListener("input", function () {
				salvarConvidadoAtual();
				if (emailConvErro && !emailConvErro.hidden) validarEmailConvidadoUI();
				atualizarBotaoConvidadosContinuar();
			});
			emailConvEl.addEventListener("blur", validarEmailConvidadoUI);
		}

		// Telefone via phone-input do design system (mesmos listeners redundantes)
		const telConvWrap = document.getElementById("vc-convidado-telefone");
		if (telConvWrap) {
			function onTelConvChange() {
				salvarConvidadoAtual();
				atualizarBotaoConvidadosContinuar();
			}
			telConvWrap.addEventListener("phone-input:change", onTelConvChange);
			const hiddenConv = telConvWrap.querySelector("[data-phone-input-value]");
			if (hiddenConv) hiddenConv.addEventListener("change", onTelConvChange);
			const numConv = telConvWrap.querySelector("[data-phone-input-number]");
			if (numConv) {
				numConv.addEventListener("input", onTelConvChange);
				numConv.addEventListener("change", onTelConvChange);
			}
		}

		// Botão "Usar meus dados" (modo pagador-recebe + 1 convite): preenche
		// o único campo de nome com o nome do pagador.
		const btnUsar = document.getElementById("vc-usar-dados-pagador");
		if (btnUsar) {
			btnUsar.addEventListener("click", function () {
				sincronizarPagador();
				if (!pagador.nome || convidados.length !== 1) return;
				convidados[0].nome = pagador.nome;
				renderNomesPagadorRecebe();
				atualizarBotaoConvidadosContinuar();
			});
		}
	}

	// ─── Aba Revisão (final) ────────────────────────────────────────────────

	function renderRevisaoFinal() {
		const dl = document.getElementById("vc-revisao-pagador");
		if (dl) {
			dl.innerHTML =
				'<div><dt>Nome</dt><dd>' + escapeHtml(pagador.nome || "—") + "</dd></div>" +
				'<div><dt>E-mail</dt><dd>' + escapeHtml(pagador.email || "—") + "</dd></div>" +
				'<div><dt>Telefone</dt><dd>' + escapeHtml(pagador.telefone || "—") + "</dd></div>";
		}

		const ul = document.getElementById("vc-revisao-convites");
		if (ul) {
			if (!convidados.length) {
				ul.innerHTML = '<li class="text-sm text-muted-foreground">Nenhum convite no pedido.</li>';
			} else {
				ul.innerHTML = convidados.map(function (c, idx) {
					const nomeHtml = "<strong>" + escapeHtml(c.nome || "Convidado " + (idx + 1)) + "</strong>";
					const detalhe = pagadorRecebe
						? ' <span class="text-sm text-muted-foreground">· QR no e-mail do pagador</span>'
						: ' <span class="text-sm text-muted-foreground">· ' + escapeHtml(c.email || "—") + "</span>";
					return '<li class="vc-revisao-convite">' +
						'<span class="vc-revisao-convite__tipo">' + escapeHtml(c.tipo_convite || "Convite") + "</span>" +
						'<span class="vc-revisao-convite__destino">' + nomeHtml + detalhe + "</span>" +
						"</li>";
				}).join("");
			}
		}

		const doacaoBloco = document.getElementById("vc-revisao-doacao-bloco");
		const doacaoEl = document.getElementById("vc-revisao-doacao");
		if (doacaoBloco && doacaoEl) {
			if (doarFlag && doacaoValor > 0) {
				doacaoBloco.hidden = false;
				doacaoEl.textContent = fmtMoeda(doacaoValor);
			} else {
				doacaoBloco.hidden = true;
			}
		}

		// Total: tenta usar último resumo conhecido, senão recalcula
		const totalEl = document.getElementById("vc-revisao-total-valor");
		if (totalEl) {
			if (ultimoResumo) {
				totalEl.textContent = fmtMoeda(ultimoResumo.total);
			} else {
				const itens = carrinhoComoArray();
				if (itens.length) {
					api("gris.api.festas.venda_convite.get_resumo_carrinho", {
						festa_name: festaSelecionada,
						itens: JSON.stringify(itens),
						doacao_valor: doarFlag ? doacaoValor : 0,
					}).then(function (resumo) {
						ultimoResumo = resumo;
						totalEl.textContent = fmtMoeda(resumo.total);
					}).catch(function () { /* mantém */ });
				}
			}
		}
	}

	// ─── Finalizar + Pagamento (dialog) ─────────────────────────────────────

	function dialogPagamentoEl() {
		return document.getElementById("vc-pagamento-dialog");
	}

	function abrirDialogPagamento() {
		const dlg = dialogPagamentoEl();
		if (!dlg) return;
		const body = document.getElementById("vc-pagamento-body");
		if (body) {
			body.innerHTML =
				'<div class="vc-pagamento-loading">' +
				'<img class="vc-pagamento-logo" src="' + escapeHtml(data.portal_logo || "/assets/gris/images/gris-character/gris-logo.png") + '" alt="Logo" />' +
				'<p class="vc-pagamento-status">Carregando…</p>' +
				"</div>";
		}
		if (!dlg.open) dlg.showModal();
	}

	function fecharDialogPagamento() {
		const dlg = dialogPagamentoEl();
		if (dlg && dlg.open) dlg.close();
	}

	function renderDialogComLink() {
		const body = document.getElementById("vc-pagamento-body");
		if (!body) return;
		const cartaoIcone =
			'<svg class="ds-lucide ds-lucide--sm" aria-hidden="true" focusable="false" viewBox="0 0 24 24">' +
			'<use href="/assets/gris/design_system/icons/lucide/sprite.svg#credit-card"></use>' +
			"</svg>";
		body.innerHTML =
			'<div class="vc-pagamento-pronto">' +
			'<p class="vc-pagamento-status">Pedido criado!</p>' +
			'<a href="' + escapeHtml(linkPagamento) + '" target="_blank" rel="noopener" class="btn-primary vc-pagamento-cta">' +
			cartaoIcone +
			'<span>Ir para pagamento</span>' +
			"</a>" +
			(pedidoNome ? '<p class="text-sm text-muted-foreground">Pedido #' + escapeHtml(pedidoNome) + "</p>" : "") +
			"</div>";
	}

	function finalizarPedido() {
		if (!festaSelecionada || !carrinhoComoArray().length) {
			toast("Adicione ao menos um convite ao carrinho.", "error");
			return;
		}
		sincronizarPagador();
		if (!pagadorRecebe) salvarConvidadoAtual();

		const btn = document.getElementById("btn-revisao-finalizar");
		if (btn) btn.disabled = true;

		abrirDialogPagamento();

		api("gris.api.festas.venda_convite.criar_convite", {
			festa_name: festaSelecionada,
			pagador: JSON.stringify(pagador),
			itens: JSON.stringify(carrinhoComoArray()),
			doacao_valor: doarFlag ? doacaoValor : 0,
			convidados: JSON.stringify(convidados),
			pagador_recebe_qr_codes: pagadorRecebe ? 1 : 0,
		})
			.then(function (resp) {
				pedidoNome = resp.convite_name;
				linkPagamento = resp.link_pagamento || "";
				if (linkPagamento) {
					renderDialogComLink();
				} else {
					startPolling();
				}
			})
			.catch(function (err) {
				fecharDialogPagamento();
				toast(err.message || "Não foi possível finalizar o pedido.", "error");
				if (btn) btn.disabled = false;
			});
	}

	function startPolling() {
		stopPolling();
		pollTries = 0;
		pollTimer = setInterval(function () {
			pollTries += 1;
			if (pollTries > 20) { stopPolling(); return; }
			api("gris.api.festas.venda_convite.get_status_pagamento", {
				convite_name: pedidoNome,
			}).then(function (resp) {
				if (resp.link_pagamento) {
					linkPagamento = resp.link_pagamento;
					renderDialogComLink();
					stopPolling();
				}
			}).catch(function () { /* ignora */ });
		}, 3000);
	}

	function stopPolling() {
		if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
	}

	// ─── Boot ───────────────────────────────────────────────────────────────

	function bindNavButtons() {
		document.querySelectorAll("[data-vc-nav]").forEach(function (btn) {
			btn.addEventListener("click", function () {
				const target = btn.getAttribute("data-vc-nav");
				// Salvaguarda: Continuar do Pedido exige pagador completo (botão já fica disabled).
				if (btn.id === "btn-pedido-continuar" && !pagadorValido()) {
					return;
				}
				if (target === "pedido") {
					renderPedido();
					// Re-valida imediatamente pra refletir o estado real do formulário
					// sem esperar a API de resumo (que pode demorar ou falhar).
					atualizarBotaoContinuarPedido();
				}
				if (target === "convidados") renderConvidados();
				if (target === "revisao") renderRevisaoFinal();
				activateTab(target);
			});
		});
		const finalizarBtn = document.getElementById("btn-revisao-finalizar");
		if (finalizarBtn) finalizarBtn.addEventListener("click", finalizarPedido);
	}

	function bindDialogGuard() {
		const dlg = dialogPagamentoEl();
		if (!dlg) return;
		// Bloqueia fechamento via ESC (close_on_overlay_click=false já cobre o overlay).
		dlg.addEventListener("cancel", function (e) { e.preventDefault(); });
	}

	function getFestaSelectValue() {
		const el = document.getElementById("vc-festa");
		if (!el) return "";
		const hidden = el.querySelector(":scope > input[type='hidden']");
		return hidden ? hidden.value : "";
	}

	function bindFestaSelect() {
		const el = document.getElementById("vc-festa");
		if (!el) return;
		el.addEventListener("change", function () {
			const novo = getFestaSelectValue();
			if (!novo || novo === festaSelecionada) return;
			trocarFestaConfirm(novo);
		});
	}

	document.addEventListener("DOMContentLoaded", function () {
		if (!data.festas || !data.festas.length) return;
		bindFestaSelect();
		bindNavButtons();
		initPedidoControls();
		initConvidadosControls();
		bindDialogGuard();
		bloquearAbas();
		// Prioridade: ?festa=<name> (validado no backend) > select (>1 festa) > única festa.
		const inicial = (data.festa_pre_selecionada || "")
			|| getFestaSelectValue()
			|| (data.festas[0] && data.festas[0].name)
			|| "";
		if (inicial) {
			// Se houve pré-seleção via query param, reflete no select também (quando existir).
			if (data.festa_pre_selecionada) {
				const selectEl = document.getElementById("vc-festa");
				const hidden = selectEl && selectEl.querySelector('input[type="hidden"]');
				if (hidden) hidden.value = data.festa_pre_selecionada;
			}
			carregarFesta(inicial);
		}
	});

	// Restauração via bfcache (botão Voltar do navegador) não reexecuta
	// DOMContentLoaded — força re-validação do botão pra refletir o que o
	// navegador acabou de restaurar nos inputs.
	window.addEventListener("pageshow", function (event) {
		if (event.persisted) atualizarBotaoContinuarPedido();
	});
})();
