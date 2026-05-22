(function () {
	"use strict";

	const data = window._portariaData || { festas: [] };

	// ─── Estado ──────────────────────────────────────────────────────────────

	let festaAtual = null;
	let convitesCache = []; // lista de entradas (filtradas) carregadas
	let entradaDetalhesAtual = null; // entrada exibida no dialog de detalhes
	let detectorScan = null; // BarcodeDetector
	let scanStream = null; // MediaStream
	let scanInterval = null;
	let scanEntradaCandidato = null;
	let scanCanvas = null; // canvas reutilizado p/ jsQR
	let jsqrLoading = null;
	let chartPizza = null;
	let chartLinha = null;
	let linhaModo = "acumulado";
	let echartsLoading = null;
	let acompanhamentoTimer = null;

	const TAB_CONVIDADOS_IDX = 1;
	const TAB_ACOMPANHAMENTO_IDX = 2;

	const STORAGE_KEY_FESTA = "portaria.festa.selecionada";

	// ─── Helpers ────────────────────────────────────────────────────────────

	function toast(message, category) {
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: {
					config: {
						category: category || "info",
						description: message,
						duration: 3500,
					},
				},
			})
		);
	}

	function escapeHtml(text) {
		const div = document.createElement("div");
		div.textContent = String(text == null ? "" : text);
		return div.innerHTML;
	}

	// Extrai a mensagem traduzida de _server_messages (JSON array) sem expor
	// o JSON bruto na UI. Cai para err.message ou texto genérico.
	function extractServerMessage(err) {
		if (!err) return "Erro de servidor.";
		if (err._server_messages) {
			try {
				const arr = JSON.parse(err._server_messages);
				if (Array.isArray(arr) && arr.length) {
					const first = arr[0];
					if (typeof first === "string") {
						try {
							const parsed = JSON.parse(first);
							return parsed.message || first;
						} catch (e) {
							return first;
						}
					}
					if (first && first.message) return first.message;
				}
			} catch (e) { /* fallback */ }
		}
		if (err.message) return err.message;
		return "Erro de servidor.";
	}

	// Bypass da frappe.call do portal: ela roda process_response no .always,
	// que loga data.exc no console.error e mostra msgprint, sem permitir
	// opt-out. Usamos fetch direto para ter controle total do fluxo de erro
	// e manter a UI consistente (toast/dialog próprio).
	// Segurança: enviamos X-Frappe-CSRF-Token e cookies de sessão; o backend
	// continua validando permissão + rate-limit em cada endpoint.
	function api(method, args) {
		const params = new URLSearchParams();
		params.append("cmd", method);
		Object.keys(args || {}).forEach(function (key) {
			let val = args[key];
			if (val === null || val === undefined) return;
			if (typeof val !== "string") val = JSON.stringify(val);
			params.append(key, val);
		});

		return fetch("/", {
			method: "POST",
			credentials: "same-origin",
			headers: {
				"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
				"X-Frappe-CSRF-Token": (window.frappe && frappe.csrf_token) || "",
				"X-Frappe-CMD": method,
				"Accept": "application/json",
				"X-Requested-With": "XMLHttpRequest",
			},
			body: params.toString(),
		}).then(function (response) {
			return response.text().then(function (text) {
				let data = null;
				if (text) {
					try { data = JSON.parse(text); } catch (e) { /* corpo não-JSON */ }
				}
				if (!response.ok) {
					throw new Error(extractServerMessage(data || {}));
				}
				if (data && data.exc) {
					throw new Error(extractServerMessage(data));
				}
				if (data && data.message !== undefined) return data.message;
				throw new Error("Resposta inesperada.");
			});
		});
	}

	function fmtData(iso) {
		if (!iso) return "—";
		const dt = new Date(iso);
		if (Number.isNaN(dt.getTime())) return "—";
		return dt.toLocaleString("pt-BR", {
			day: "2-digit",
			month: "2-digit",
			year: "numeric",
			hour: "2-digit",
			minute: "2-digit",
		});
	}

	function fmtHora(iso) {
		if (!iso) return "—";
		const dt = new Date(iso);
		if (Number.isNaN(dt.getTime())) return "—";
		return dt.toLocaleTimeString("pt-BR", {
			hour: "2-digit",
			minute: "2-digit",
		});
	}

	function getSelectValue(id) {
		const el = document.getElementById(id);
		if (!el) return "";
		const hidden = el.querySelector('input[type="hidden"]');
		if (hidden) return hidden.value || "";
		if (el.tagName === "SELECT") return el.value || "";
		return "";
	}

	function setSelectValue(id, value) {
		const el = document.getElementById(id);
		if (!el) return;
		const hidden = el.querySelector('input[type="hidden"]');
		if (hidden) hidden.value = value;
		if (el.tagName === "SELECT") el.value = value;
	}

	function debounce(fn, ms) {
		let t = null;
		return function () {
			const args = arguments;
			const self = this;
			clearTimeout(t);
			t = setTimeout(function () { fn.apply(self, args); }, ms);
		};
	}

	function ensureECharts() {
		if (window.echarts) return Promise.resolve();
		if (echartsLoading) return echartsLoading;
		echartsLoading = new Promise(function (resolve, reject) {
			const s = document.createElement("script");
			s.src = "/assets/gris/vendor/echarts/echarts.min.js";
			s.onload = function () {
				if (window.echarts) resolve();
				else reject(new Error("ECharts não carregou."));
			};
			s.onerror = function () { reject(new Error("Falha ao carregar ECharts.")); };
			document.head.appendChild(s);
		});
		return echartsLoading;
	}

	function ensureJsQR() {
		if (window.jsQR) return Promise.resolve();
		if (jsqrLoading) return jsqrLoading;
		jsqrLoading = new Promise(function (resolve, reject) {
			const s = document.createElement("script");
			s.src = "/assets/gris/vendor/jsqr/jsQR.js";
			s.onload = function () {
				if (window.jsQR) resolve();
				else reject(new Error("jsQR não carregou."));
			};
			s.onerror = function () { reject(new Error("Falha ao carregar jsQR.")); };
			document.head.appendChild(s);
		});
		return jsqrLoading;
	}

	// ─── Seleção de festa ───────────────────────────────────────────────────

	function setFestaAtual(festaName) {
		festaAtual = festaName || null;
		try {
			if (festaName) sessionStorage.setItem(STORAGE_KEY_FESTA, festaName);
		} catch (e) { /* sessionStorage indisponível */ }
		const festaObj = (data.festas || []).find(function (x) { return x.name === festaName; });
		const sub = document.getElementById("portaria-festa-subtitle");
		if (sub) {
			sub.textContent = festaObj
				? "Operando: " + (festaObj.nome_festa || festaName)
				: "Selecione a festa para começar.";
		}
		const btnScan = document.getElementById("btn-portaria-scan");
		const btnVender = document.getElementById("btn-portaria-vender");
		if (btnScan) btnScan.disabled = !festaName;
		if (btnVender) {
			const vendaAtiva = !!(festaObj && festaObj.venda_na_portaria);
			btnVender.disabled = !festaName || !vendaAtiva;
			btnVender.title = (!festaName || vendaAtiva)
				? ""
				: "Venda na portaria não está ativa para esta festa.";
		}
		if (festaName) {
			carregarLista();
		}
	}

	function inicializarFesta() {
		const festas = data.festas || [];
		if (festas.length === 0) return;

		if (festas.length === 1) {
			setFestaAtual(festas[0].name);
			return;
		}

		// >1 festa: usa o sessionStorage se válido; senão deixa o select
		let inicial = "";
		try { inicial = sessionStorage.getItem(STORAGE_KEY_FESTA) || ""; } catch (e) { /* idem */ }
		const valida = festas.find(function (f) { return f.name === inicial; });
		if (valida) {
			setSelectValue("portaria-festa", inicial);
			setFestaAtual(inicial);
		}

		const sel = document.getElementById("portaria-festa");
		if (sel) {
			sel.addEventListener("change", function () {
				const novo = getSelectValue("portaria-festa");
				if (!novo) return;
				setFestaAtual(novo);
			});
		}
	}

	// ─── Scanner QR ─────────────────────────────────────────────────────────

	function abrirScanner() {
		if (!festaAtual) {
			toast("Selecione uma festa primeiro.", "error");
			return;
		}
		scanEntradaCandidato = null;
		const dlg = document.getElementById("dlg-portaria-scan");
		const wrapper = document.getElementById("portaria-scan-video-wrapper");
		const manual = document.getElementById("portaria-scan-manual");
		const resultado = document.getElementById("portaria-scan-resultado");
		const statusEl = document.getElementById("portaria-scan-status");
		const confirmar = document.getElementById("btn-portaria-scan-confirmar");
		const toggleManual = document.getElementById("btn-portaria-toggle-manual");
		const voltarCamera = document.getElementById("btn-portaria-voltar-camera");
		const manualHint = document.getElementById("portaria-scan-manual-hint");
		if (resultado) resultado.hidden = true;
		if (confirmar) confirmar.disabled = true;
		if (statusEl) statusEl.textContent = "Solicitando permissão da câmera…";
		if (wrapper) wrapper.hidden = false;
		if (manual) manual.hidden = true;
		if (toggleManual) toggleManual.hidden = true;
		if (voltarCamera) voltarCamera.hidden = true;
		if (manualHint) manualHint.textContent = "Digite o código do convite manualmente:";
		if (dlg && typeof dlg.showModal === "function") dlg.showModal();

		// Câmera precisa de HTTPS (ou localhost) e API mediaDevices.
		if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
			if (statusEl) {
				statusEl.textContent =
					"Câmera não suportada por este navegador. Use o campo manual abaixo.";
			}
			if (wrapper) wrapper.hidden = true;
			if (manual) manual.hidden = false;
			if (manualHint) {
				manualHint.textContent =
					"Câmera/QR scanner não disponível neste navegador. Digite o código manualmente:";
			}
			return;
		}

		// Decisão do decoder: BarcodeDetector nativo se disponível (Android,
		// macOS recente); senão jsQR (puro JS) para Linux/Windows/Firefox.
		const usarNativo = "BarcodeDetector" in window;
		if (usarNativo) {
			try {
				detectorScan = new window.BarcodeDetector({ formats: ["qr_code"] });
			} catch (e) {
				detectorScan = null;
			}
		}
		const decoderReady = detectorScan
			? Promise.resolve()
			: ensureJsQR().catch(function (err) {
				if (statusEl) {
					statusEl.textContent =
						"Não foi possível carregar o leitor de QR. Use o campo manual abaixo.";
				}
				if (wrapper) wrapper.hidden = true;
				if (manual) manual.hidden = false;
				if (manualHint) {
					manualHint.textContent =
						"Não foi possível carregar o leitor de QR. Digite o código manualmente:";
				}
				throw err;
			});

		decoderReady
			.then(function () {
				return navigator.mediaDevices.getUserMedia({
					video: { facingMode: "environment" },
				});
			})
			.then(function (stream) {
				scanStream = stream;
				const video = document.getElementById("portaria-scan-video");
				if (!video) return;
				video.srcObject = stream;
				if (statusEl) statusEl.textContent = "Aponte para o QR code…";
				if (toggleManual) toggleManual.hidden = false;
				if (!scanCanvas) scanCanvas = document.createElement("canvas");

				const scan = function () {
					if (!video.videoWidth) return;
					if (detectorScan) {
						detectorScan
							.detect(video)
							.then(function (codigos) {
								if (codigos && codigos.length) {
									const payload = (codigos[0].rawValue || "").trim();
									if (payload) {
										pararCamera();
										processarCodigo(payload);
									}
								}
							})
							.catch(function () { /* frames inválidos */ });
						return;
					}
					// Fallback jsQR: copia frame para canvas e decodifica.
					if (!window.jsQR) return;
					scanCanvas.width = video.videoWidth;
					scanCanvas.height = video.videoHeight;
					const ctx = scanCanvas.getContext("2d", { willReadFrequently: true });
					ctx.drawImage(video, 0, 0, scanCanvas.width, scanCanvas.height);
					const imageData = ctx.getImageData(0, 0, scanCanvas.width, scanCanvas.height);
					const code = window.jsQR(imageData.data, imageData.width, imageData.height, {
						inversionAttempts: "dontInvert",
					});
					if (code && code.data) {
						const payload = code.data.trim();
						if (payload) {
							pararCamera();
							processarCodigo(payload);
						}
					}
				};
				// Polling mais rápido para jsQR (decode é leve em canvas pequeno).
				scanInterval = setInterval(scan, detectorScan ? 400 : 250);
			})
			.catch(function (err) {
				if (statusEl) {
					statusEl.textContent =
						"Permissão de câmera negada ou indisponível. Use o campo manual abaixo.";
				}
				if (wrapper) wrapper.hidden = true;
				if (manual) manual.hidden = false;
				if (manualHint) {
					manualHint.textContent =
						"Permissão de câmera negada ou indisponível. Digite o código manualmente:";
				}
			});
	}

	function pararCamera() {
		if (scanInterval) {
			clearInterval(scanInterval);
			scanInterval = null;
		}
		if (scanStream) {
			scanStream.getTracks().forEach(function (t) { t.stop(); });
			scanStream = null;
		}
		const video = document.getElementById("portaria-scan-video");
		if (video) video.srcObject = null;
	}

	function fecharScanner() {
		pararCamera();
		scanEntradaCandidato = null;
		const dlg = document.getElementById("dlg-portaria-scan");
		if (dlg && dlg.open) dlg.close();
	}

	function processarCodigo(codigo) {
		api("gris.api.festas.portaria.consultar_convite", {
			festa: festaAtual,
			codigo: codigo,
		})
			.then(function (entrada) {
				if (!entrada || entrada.valido === false) {
					fecharScanner();
					mostrarCodigoInvalido();
					return;
				}
				if (entrada.ja_entrou) {
					fecharScanner();
					mostrarJaEntrou(entrada);
					return;
				}
				scanEntradaCandidato = entrada;
				const statusEl = document.getElementById("portaria-scan-status");
				if (statusEl) statusEl.textContent = "Convite válido. Confirme a entrada.";
				const wrapper = document.getElementById("portaria-scan-video-wrapper");
				if (wrapper) wrapper.hidden = true;
				const manual = document.getElementById("portaria-scan-manual");
				if (manual) manual.hidden = true;
				const resultado = document.getElementById("portaria-scan-resultado");
				if (resultado) resultado.hidden = false;
				const setText = function (id, val) {
					const el = document.getElementById(id);
					if (el) el.textContent = val || "—";
				};
				setText("portaria-scan-nome", entrada.nome_convidado);
				setText("portaria-scan-email", entrada.email);
				setText("portaria-scan-telefone", entrada.telefone);
				setText("portaria-scan-pagador", entrada.nome_pagador);
				setText("portaria-scan-pagador-email", entrada.email_pagador);
				setText("portaria-scan-pagador-telefone", entrada.telefone_pagador);
				setText("portaria-scan-codigo", entrada.codigo);
				const confirmar = document.getElementById("btn-portaria-scan-confirmar");
				if (confirmar) confirmar.disabled = false;
			})
			.catch(function (err) {
				fecharScanner();
				mostrarCodigoInvalido(err && err.message);
			});
	}

	function mostrarCodigoInvalido(mensagem) {
		const dlg = document.getElementById("dlg-portaria-codigo-invalido");
		const msg = document.getElementById("portaria-codigo-invalido-mensagem");
		// Mensagem genérica do backend; nunca expõe se o código existe em outra festa.
		if (msg) msg.textContent = mensagem || "Este código de convite não é válido para esta festa.";
		if (!dlg || typeof dlg.showModal !== "function") return;
		if (dlg.open) return;
		dlg.showModal();
	}

	function mostrarJaEntrou(entrada) {
		const dlg = document.getElementById("dlg-portaria-ja-entrou");
		const msg = document.getElementById("portaria-ja-entrou-mensagem");
		const nome = document.getElementById("portaria-ja-entrou-nome");
		const hora = document.getElementById("portaria-ja-entrou-hora");
		const por = document.getElementById("portaria-ja-entrou-por");
		if (msg) msg.textContent = "Este convidado já registrou entrada anteriormente.";
		if (nome) nome.textContent = entrada.nome_convidado || "—";
		if (hora) hora.textContent = fmtData(entrada.hora_entrada);
		if (por) por.textContent = entrada.registrado_por || "—";
		if (dlg && typeof dlg.showModal === "function") dlg.showModal();
	}

	function confirmarEntrada() {
		if (!scanEntradaCandidato) return;
		const confirmar = document.getElementById("btn-portaria-scan-confirmar");
		if (confirmar) confirmar.disabled = true;
		api("gris.api.festas.portaria.marcar_entrada", {
			festa: festaAtual,
			codigo: scanEntradaCandidato.codigo,
		})
			.then(function (resp) {
				fecharScanner();
				if (!resp || resp.valido === false) {
					mostrarCodigoInvalido();
					return;
				}
				if (resp.ja_entrou_antes) {
					mostrarJaEntrou(resp);
				} else {
					toast("Entrada confirmada: " + (resp.nome_convidado || ""), "success");
				}
				carregarLista();
				if (chartPizza) carregarAcompanhamento();
			})
			.catch(function (err) {
				toast(err.message || "Falha ao confirmar entrada.", "error");
				if (confirmar) confirmar.disabled = false;
			});
	}

	// ─── Tabela / Lista de convidados ──────────────────────────────────────

	function renderTabela(linhas) {
		const container = document.getElementById("portaria-tabela-container");
		const vazio = document.getElementById("portaria-tabela-vazia");
		if (!container) return;
		if (!linhas || !linhas.length) {
			container.innerHTML = "";
			if (vazio) vazio.hidden = false;
			return;
		}
		if (vazio) vazio.hidden = true;

		const linhasHtml = linhas
			.map(function (e) {
				const statusBadge = e.ja_entrou
					? '<span class="badge badge-success">Entrou</span>'
					: '<span class="badge badge-secondary">Não entrou</span>';
				const hora = e.hora_entrada ? fmtHora(e.hora_entrada) : "—";
				const acoes =
					'<button type="button" class="btn-sm-outline" data-acao="detalhes" data-name="' +
					escapeHtml(e.name) +
					'">Detalhes</button>';
				return (
					"<tr>" +
					"<td>" + escapeHtml(e.nome_convidado || "—") + "</td>" +
					"<td>" + statusBadge + "</td>" +
					"<td>" + hora + "</td>" +
					"<td>" + acoes + "</td>" +
					"</tr>"
				);
			})
			.join("");

		container.innerHTML =
			'<table class="table portaria-table">' +
			"<thead><tr>" +
			"<th>Nome</th>" +
			"<th>Status</th>" +
			"<th>Hora de entrada</th>" +
			"<th>Ações</th>" +
			"</tr></thead>" +
			"<tbody>" + linhasHtml + "</tbody>" +
			"</table>";

		// Bind das ações
		container.querySelectorAll('[data-acao]').forEach(function (btn) {
			btn.addEventListener("click", function () {
				const acao = btn.getAttribute("data-acao");
				const name = btn.getAttribute("data-name");
				const entrada = convitesCache.find(function (e) { return e.name === name; });
				if (!entrada) return;
				if (acao === "detalhes") abrirDetalhes(entrada);
			});
		});
	}

	function carregarLista() {
		if (!festaAtual) return Promise.resolve();
		const nome = (document.getElementById("portaria-filtro-nome") || {}).value || "";
		const status = getSelectValue("portaria-filtro-status") || "";
		return api("gris.api.festas.portaria.listar_entradas", {
			festa: festaAtual,
			nome: nome,
			status: status,
		})
			.then(function (resp) {
				convitesCache = (resp && resp.entradas) || [];
				renderTabela(convitesCache);
			})
			.catch(function (err) {
				toast(err.message || "Falha ao carregar a lista.", "error");
			});
	}

	function abrirDetalhes(entrada) {
		entradaDetalhesAtual = entrada;
		const dlg = document.getElementById("dlg-portaria-detalhes");
		const set = function (id, val) {
			const el = document.getElementById(id);
			if (el) el.textContent = val || "—";
		};
		set("portaria-det-nome", entrada.nome_convidado);
		set("portaria-det-email", entrada.email);
		set("portaria-det-telefone", entrada.telefone);
		set("portaria-det-codigo", entrada.codigo);
		set("portaria-det-hora", entrada.hora_entrada ? fmtData(entrada.hora_entrada) : "—");
		set("portaria-det-por", entrada.registrado_por);
		set("portaria-det-convite", entrada.convite);

		const statusEl = document.getElementById("portaria-det-status");
		if (statusEl) {
			statusEl.innerHTML = "";
			const badge = document.createElement("span");
			if (entrada.ja_entrou) {
				badge.className = "badge badge-success";
				badge.textContent = "Entrou";
			} else {
				badge.className = "badge badge-secondary";
				badge.textContent = "Não entrou";
			}
			statusEl.appendChild(badge);
		}

		if (dlg && typeof dlg.showModal === "function") dlg.showModal();
	}

	function abrirEditar(entrada) {
		const dlg = document.getElementById("dlg-portaria-editar");
		const hidden = document.getElementById("portaria-editar-name");
		const nomeEl = document.getElementById("portaria-editar-nome");
		const emailEl = document.getElementById("portaria-editar-email");
		const telEl = document.getElementById("portaria-editar-telefone");
		if (hidden) hidden.value = entrada.name;
		if (nomeEl) nomeEl.textContent = entrada.nome_convidado || "—";
		if (emailEl) emailEl.value = entrada.email || "";
		if (telEl) telEl.value = entrada.telefone || "";
		if (dlg && typeof dlg.showModal === "function") dlg.showModal();
	}

	function salvarEdicao() {
		const name = (document.getElementById("portaria-editar-name") || {}).value || "";
		if (!name) return;
		const email = (document.getElementById("portaria-editar-email") || {}).value || "";
		const telefone = (document.getElementById("portaria-editar-telefone") || {}).value || "";
		const btn = document.getElementById("btn-portaria-editar-salvar");
		if (btn) btn.disabled = true;
		api("gris.api.festas.portaria.editar_dados_convidado", {
			lista_entrada_name: name,
			email: email,
			telefone: telefone,
		})
			.then(function () {
				toast("Dados atualizados.", "success");
				const dlg = document.getElementById("dlg-portaria-editar");
				if (dlg && dlg.open) dlg.close();
				carregarLista();
			})
			.catch(function (err) {
				toast(err.message || "Falha ao salvar.", "error");
			})
			.finally(function () {
				if (btn) btn.disabled = false;
			});
	}

	function confirmarReenvio(entrada) {
		if (!window.confirm("Reenviar QR code para " + (entrada.email || entrada.nome_convidado) + "?")) {
			return;
		}
		api("gris.api.festas.portaria.reenviar_convite", {
			lista_entrada_name: entrada.name,
		})
			.then(function () {
				toast("Reenvio enfileirado. O e-mail será enviado em instantes.", "success");
			})
			.catch(function (err) {
				toast(err.message || "Falha no reenvio.", "error");
			});
	}

	// ─── Vender na porta ────────────────────────────────────────────────────

	function abrirVender() {
		if (!festaAtual) {
			toast("Selecione uma festa primeiro.", "error");
			return;
		}
		const dlg = document.getElementById("dlg-portaria-vender");
		const urlEl = document.getElementById("portaria-vender-qr-url");
		if (urlEl) urlEl.textContent = "";
		const img = document.getElementById("portaria-vender-qr");
		if (img) img.removeAttribute("src");
		api("gris.api.festas.portaria.get_url_venda_porta", { festa: festaAtual })
			.then(function (resp) {
				const link = document.getElementById("btn-portaria-abrir-venda");
				if (link) link.setAttribute("href", resp.url);
				if (img && resp.qr_data_uri) img.src = resp.qr_data_uri;
				if (urlEl) urlEl.textContent = resp.url;
				if (dlg && typeof dlg.showModal === "function") dlg.showModal();
			})
			.catch(function (err) {
				toast(err.message || "Não foi possível preparar a venda.", "error");
			});
	}

	// ─── Acompanhamento (gráficos) ─────────────────────────────────────────

	// Paleta acessível (Wong, daltonismo-friendly)
	const COR_ENTROU = "#009E73";
	const COR_NAO_ENTROU = "#D55E00";
	const COR_LINHA = "#0072B2";

	function carregarAcompanhamento() {
		if (!festaAtual) return Promise.resolve();
		return api("gris.api.festas.portaria.get_acompanhamento", { festa: festaAtual })
			.then(function (resp) {
				return ensureECharts().then(function () {
					renderPizza(resp.pizza);
					renderLinha(resp.linha);
				});
			})
			.catch(function (err) {
				toast(err.message || "Falha ao carregar gráficos.", "error");
			});
	}

	function renderPizza(pizza) {
		const el = document.getElementById("chart-portaria-pizza");
		if (!el) return;
		if (!chartPizza) {
			chartPizza = window.echarts.init(el);
			window.addEventListener("resize", function () {
				if (chartPizza) chartPizza.resize();
			});
		}
		const total = Number((pizza && pizza.total) || 0);
		const entrou = Number((pizza && pizza.entrou) || 0);
		const naoEntrou = Number((pizza && pizza.nao_entrou) || 0);
		chartPizza.setOption({
			tooltip: { trigger: "item" },
			legend: { bottom: 0 },
			color: [COR_ENTROU, COR_NAO_ENTROU],
			series: [
				{
					name: "Entradas",
					type: "pie",
					radius: ["45%", "70%"],
					avoidLabelOverlap: true,
					label: {
						show: true,
						formatter: function (p) {
							return p.name + "\n" + p.value + " (" + p.percent + "%)";
						},
					},
					data: [
						{ value: entrou, name: "Entrou" },
						{ value: naoEntrou, name: "Não entrou" },
					],
				},
			],
			graphic: total === 0 ? [
				{
					type: "text",
					left: "center",
					top: "middle",
					style: {
						text: "Sem dados ainda",
						fill: "#888",
						font: "14px sans-serif",
					},
				},
			] : undefined,
		});
	}

	function renderLinha(linhaRaw) {
		const el = document.getElementById("chart-portaria-linha");
		if (!el) return;
		if (!chartLinha) {
			chartLinha = window.echarts.init(el);
			window.addEventListener("resize", function () {
				if (chartLinha) chartLinha.resize();
			});
		}
		const linha = (linhaRaw || []);
		const xs = linha.map(function (p) {
			const dt = new Date(p.bin);
			return dt.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
		});
		const valores = linha.map(function (p) {
			return linhaModo === "acumulado" ? Number(p.acumulado || 0) : Number(p.qtd || 0);
		});

		chartLinha.setOption({
			tooltip: { trigger: "axis" },
			color: [COR_LINHA],
			grid: { left: 40, right: 16, top: 20, bottom: 40 },
			xAxis: {
				type: "category",
				data: xs,
				axisLabel: { interval: Math.floor(Math.max(0, xs.length / 8)) },
			},
			yAxis: { type: "value", minInterval: 1 },
			series: [
				{
					name: linhaModo === "acumulado" ? "Acumulado" : "Por janela (15 min)",
					type: "line",
					smooth: true,
					data: valores,
					areaStyle: linhaModo === "acumulado" ? { opacity: 0.15 } : undefined,
				},
			],
		});
	}

	// ─── Polling / Tab visibility ──────────────────────────────────────────

	function tabAtiva() {
		const triggers = document.querySelectorAll('#portaria-tabs [role="tab"]');
		for (let i = 0; i < triggers.length; i++) {
			if (triggers[i].getAttribute("aria-selected") === "true") {
				return i + 1; // 1-based para coincidir com setup
			}
		}
		return 0;
	}

	function iniciarAcompanhamentoPoll() {
		pararAcompanhamentoPoll();
		acompanhamentoTimer = setInterval(function () {
			if (document.hidden) return;
			if (tabAtiva() === TAB_ACOMPANHAMENTO_IDX) carregarAcompanhamento();
			else if (tabAtiva() === TAB_CONVIDADOS_IDX) carregarLista();
		}, 30000);
	}

	function pararAcompanhamentoPoll() {
		if (acompanhamentoTimer) {
			clearInterval(acompanhamentoTimer);
			acompanhamentoTimer = null;
		}
	}

	// ─── Bindings ──────────────────────────────────────────────────────────

	function bindUI() {
		const btnScan = document.getElementById("btn-portaria-scan");
		if (btnScan) btnScan.addEventListener("click", abrirScanner);
		const btnVender = document.getElementById("btn-portaria-vender");
		if (btnVender) btnVender.addEventListener("click", abrirVender);

		const btnCancelar = document.getElementById("btn-portaria-scan-cancelar");
		if (btnCancelar) btnCancelar.addEventListener("click", fecharScanner);
		const btnConfirmar = document.getElementById("btn-portaria-scan-confirmar");
		if (btnConfirmar) btnConfirmar.addEventListener("click", confirmarEntrada);

		const btnValidarManual = document.getElementById("btn-portaria-validar-codigo");
		if (btnValidarManual) {
			btnValidarManual.addEventListener("click", function () {
				const codigo = ((document.getElementById("portaria-scan-codigo-manual") || {}).value || "").trim();
				if (!codigo) {
					toast("Digite o código.", "error");
					return;
				}
				processarCodigo(codigo);
			});
		}

		const btnToggleManual = document.getElementById("btn-portaria-toggle-manual");
		if (btnToggleManual) {
			btnToggleManual.addEventListener("click", function () {
				pararCamera();
				const wrapper = document.getElementById("portaria-scan-video-wrapper");
				const manual = document.getElementById("portaria-scan-manual");
				const voltar = document.getElementById("btn-portaria-voltar-camera");
				const input = document.getElementById("portaria-scan-codigo-manual");
				if (wrapper) wrapper.hidden = true;
				if (manual) manual.hidden = false;
				if (voltar) voltar.hidden = false;
				btnToggleManual.hidden = true;
				if (input) {
					input.value = "";
					input.focus();
				}
			});
		}

		const btnVoltarCamera = document.getElementById("btn-portaria-voltar-camera");
		if (btnVoltarCamera) {
			btnVoltarCamera.addEventListener("click", function () {
				abrirScanner();
			});
		}

		const btnTentarDeNovo = document.getElementById("btn-portaria-codigo-invalido-tentar");
		if (btnTentarDeNovo) {
			btnTentarDeNovo.addEventListener("click", function () {
				const dlg = document.getElementById("dlg-portaria-codigo-invalido");
				if (dlg && dlg.open) dlg.close();
				abrirScanner();
			});
		}

		const btnEditar = document.getElementById("btn-portaria-editar-salvar");
		if (btnEditar) btnEditar.addEventListener("click", salvarEdicao);

		const btnDetEditar = document.getElementById("btn-portaria-det-editar");
		if (btnDetEditar) {
			btnDetEditar.addEventListener("click", function () {
				if (!entradaDetalhesAtual) return;
				const dlgDet = document.getElementById("dlg-portaria-detalhes");
				if (dlgDet && dlgDet.open) dlgDet.close();
				abrirEditar(entradaDetalhesAtual);
			});
		}

		const btnDetReenviar = document.getElementById("btn-portaria-det-reenviar");
		if (btnDetReenviar) {
			btnDetReenviar.addEventListener("click", function () {
				if (!entradaDetalhesAtual) return;
				confirmarReenvio(entradaDetalhesAtual);
			});
		}

		const filtroNome = document.getElementById("portaria-filtro-nome");
		if (filtroNome) filtroNome.addEventListener("input", debounce(carregarLista, 300));
		const filtroStatus = document.getElementById("portaria-filtro-status");
		if (filtroStatus) filtroStatus.addEventListener("change", carregarLista);

		document.querySelectorAll(".portaria-chart-mode").forEach(function (btn) {
			btn.addEventListener("click", function () {
				const modo = btn.getAttribute("data-modo");
				if (!modo) return;
				linhaModo = modo;
				document.querySelectorAll(".portaria-chart-mode").forEach(function (b) {
					b.setAttribute("aria-pressed", b.getAttribute("data-modo") === modo ? "true" : "false");
				});
				carregarAcompanhamento();
			});
		});

		// Quando o usuário ativa a aba Acompanhamento pela primeira vez,
		// dispara o carregamento; também atualiza ao tocar a aba.
		document.querySelectorAll('#portaria-tabs [role="tab"]').forEach(function (tab) {
			tab.addEventListener("click", function () {
				setTimeout(function () {
					const idx = tabAtiva();
					if (idx === TAB_ACOMPANHAMENTO_IDX) carregarAcompanhamento();
					else if (idx === TAB_CONVIDADOS_IDX) carregarLista();
				}, 50);
			});
		});

		// Fechar dialog do scanner solta a câmera.
		const dlgScan = document.getElementById("dlg-portaria-scan");
		if (dlgScan) dlgScan.addEventListener("close", function () { pararCamera(); });
	}

	document.addEventListener("DOMContentLoaded", function () {
		bindUI();
		inicializarFesta();
		iniciarAcompanhamentoPoll();
	});

	window.addEventListener("beforeunload", function () {
		pararCamera();
		pararAcompanhamentoPoll();
	});
})();
