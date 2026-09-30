// Documentos de transparência: lista por ano, filtros e dialog de cadastro/edição.
(function () {
	const raiz = document.querySelector(".adm-transparencia");
	if (!raiz) return;

	const REGRAS = lerJson(raiz.dataset.regras, {});
	const TIPOS_COM_CARTORIO = REGRAS.tipos_com_cartorio || [];
	const dialogDocumento = document.getElementById("dialog-transparencia");
	const dialogExclusao = document.getElementById("dialog-excluir-transparencia");
	const HOJE = hojeIso();

	let documentos = lerJson(raiz.dataset.documentos, []);
	let filtro = "todos";
	let busca = "";
	// O arquivo que vai no save: o do documento em edição, ou o que acabou de ser enviado.
	let arquivoDoFormulario = null;

	function lerJson(texto, padrao) {
		try {
			return JSON.parse(texto || "null") || padrao;
		} catch (e) {
			return padrao;
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

	function textoSimples(html) {
		const doc = new DOMParser().parseFromString(String(html == null ? "" : html), "text/html");
		return (doc.body.textContent || "").trim();
	}

	function semAcento(texto) {
		return String(texto || "")
			.normalize("NFD")
			.replace(/[̀-ͯ]/g, "")
			.toLowerCase();
	}

	function toast(categoria, titulo) {
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: { config: { category: categoria, title: titulo, duration: 4500 } },
			})
		);
	}

	function hojeIso() {
		const d = new Date();
		const mes = String(d.getMonth() + 1).padStart(2, "0");
		const dia = String(d.getDate()).padStart(2, "0");
		return `${d.getFullYear()}-${mes}-${dia}`;
	}

	function dataBR(iso) {
		const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
		return match ? `${match[3]}/${match[2]}/${match[1]}` : "";
	}

	function definirData(id, iso) {
		// O datepicker expõe `value` (ISO) na raiz; vazio limpa o campo.
		const elemento = document.getElementById(id);
		if (elemento) elemento.value = iso || "";
	}

	function valorDaData(id) {
		const elemento = document.getElementById(id);
		return (elemento && elemento.value) || "";
	}

	function switchDe(id) {
		const rotulo = document.getElementById(id);
		return rotulo ? rotulo.querySelector('input[type="checkbox"]') : null;
	}

	function definirSelect(id, valor) {
		// O select expõe `value` na raiz; escrever no hidden não atualizaria o rótulo.
		const elemento = document.getElementById(id);
		if (elemento) elemento.value = valor == null ? "" : String(valor);
	}

	function valorDoSelect(id) {
		const elemento = document.getElementById(id);
		if (!elemento) return "";
		const hidden = elemento.querySelector('input[type="hidden"]');
		return hidden ? hidden.value : "";
	}

	function urlDoArquivo(arquivo) {
		const url = String(arquivo || "");
		return /^(\/|https?:\/\/)/.test(url) ? url : "";
	}

	function nomeDoArquivo(arquivo) {
		const nome = String(arquivo || "")
			.split("/")
			.pop();
		try {
			return decodeURIComponent(nome);
		} catch (e) {
			return nome;
		}
	}

	// `frappe.call` no portal engole a mensagem do `frappe.throw`, e é ela que diz
	// por que a gravação foi recusada.
	async function chamar(metodo, args) {
		const resposta = await fetch(`/api/method/${metodo}`, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				Accept: "application/json",
				"X-Frappe-CSRF-Token": frappe.csrf_token || "",
			},
			credentials: "same-origin",
			body: JSON.stringify(args),
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

	// ------------------------------------------------------------------
	// Lista
	// ------------------------------------------------------------------

	function porName(name) {
		return documentos.find((doc) => doc.name === name) || null;
	}

	function estaVencido(doc) {
		return Boolean(doc.data_validade && doc.data_validade < HOJE);
	}

	function descricaoCurta(doc) {
		return [doc.tipo_arquivo, doc.ano_referencia].filter(Boolean).join(" · ");
	}

	function detalhes(doc) {
		const partes = [doc.area || "Sem área"];
		if (doc.data_emissao) partes.push(`emitido em ${dataBR(doc.data_emissao)}`);
		if (doc.data_validade) partes.push(`válido até ${dataBR(doc.data_validade)}`);
		if (doc.registrado_em_cartorio) partes.push("registrado em cartório");
		if (doc.atualizado_em) partes.push(`atualizado em ${dataBR(doc.atualizado_em)}`);
		return partes.map(escapeHtml).join(" · ");
	}

	function renderizarLinha(doc) {
		const selos = [
			doc.publicado
				? `<span class="badge">${icone("globe", "xs")} Publicado</span>`
				: `<span class="badge-outline">${icone("eye-off", "xs")} Não publicado</span>`,
		];
		if (estaVencido(doc)) selos.push('<span class="badge-destructive">Vencido</span>');

		const url = urlDoArquivo(doc.arquivo);
		const abrir = url
			? `<a class="btn-sm-ghost" href="${escapeHtml(
					url
			  )}" target="_blank" rel="noopener">${icone(
					"external-link",
					"xs"
			  )}<span>Abrir</span></a>`
			: "";
		const publicar = doc.publicado
			? `${icone("eye-off", "xs")}<span>Despublicar</span>`
			: `${icone("globe", "xs")}<span>Publicar</span>`;
		const name = escapeHtml(doc.name);

		return `<li class="adm-transparencia__linha">
			<div class="adm-transparencia__info">
				<p class="adm-transparencia__tipo">${escapeHtml(doc.tipo_arquivo)}</p>
				<p class="adm-transparencia__meta">${detalhes(doc)}</p>
			</div>
			<div class="adm-transparencia__selos">${selos.join("")}</div>
			<div class="adm-transparencia__acoes">
				${abrir}
				<button type="button" class="btn-sm-ghost" data-acao="publicar" data-name="${name}">${publicar}</button>
				<button type="button" class="btn-sm-outline" data-acao="editar" data-name="${name}">${icone(
			"pencil",
			"xs"
		)}<span>Editar</span></button>
			</div>
		</li>`;
	}

	function filtrados() {
		// Cada palavra casa sozinha: "certidao 2025" acha a certidão federal de 2025.
		const palavras = semAcento(busca).split(/\s+/).filter(Boolean);
		return documentos.filter((doc) => {
			if (filtro === "publicados" && !doc.publicado) return false;
			if (filtro === "nao_publicados" && doc.publicado) return false;
			if (!palavras.length) return true;
			const alvo = semAcento(
				[doc.tipo_arquivo, doc.area || "sem área", doc.ano_referencia].join(" ")
			);
			return palavras.every((palavra) => alvo.includes(palavra));
		});
	}

	function plural(n) {
		return `${n} ${n === 1 ? "documento" : "documentos"}`;
	}

	function renderizar() {
		const vazio = document.getElementById("transparencia-vazio");
		const conteudo = document.getElementById("transparencia-conteudo");
		vazio.hidden = documentos.length > 0;
		conteudo.hidden = documentos.length === 0;
		if (!documentos.length) return;

		const lista = filtrados();
		const contagem = document.getElementById("transparencia-contagem");
		contagem.textContent =
			lista.length === documentos.length
				? plural(documentos.length)
				: `${lista.length} de ${plural(documentos.length)}`;
		document.getElementById("transparencia-sem-resultado").hidden = lista.length > 0;

		// A ordem vem do servidor (ano mais recente primeiro); aqui só se agrupa.
		const grupos = [];
		lista.forEach((doc) => {
			const ultimo = grupos[grupos.length - 1];
			if (ultimo && ultimo.ano === doc.ano_referencia) ultimo.docs.push(doc);
			else grupos.push({ ano: doc.ano_referencia, docs: [doc] });
		});

		document.getElementById("transparencia-lista").innerHTML = grupos
			.map(
				(grupo) => `<section class="adm-transparencia__ano" aria-label="${escapeHtml(
					grupo.ano
				)}">
					<header class="adm-transparencia__ano-cabecalho">
						<h2 class="adm-transparencia__ano-titulo">${escapeHtml(grupo.ano)}</h2>
						<span class="adm-transparencia__ano-contagem">${plural(grupo.docs.length)}</span>
					</header>
					<article class="card adm-transparencia__card">
						<ul class="adm-transparencia__linhas">${grupo.docs.map(renderizarLinha).join("")}</ul>
					</article>
				</section>`
			)
			.join("");
	}

	function aplicarFiltro(novo) {
		filtro = novo;
		document.querySelectorAll(".adm-transparencia__filtro [data-filtro]").forEach((botao) => {
			const ativo = botao.dataset.filtro === novo;
			botao.setAttribute("aria-pressed", ativo ? "true" : "false");
			botao.classList.toggle("btn-sm-secondary", ativo);
			botao.classList.toggle("btn-sm-ghost", !ativo);
		});
		renderizar();
	}

	// ------------------------------------------------------------------
	// Dialog de cadastro/edição
	// ------------------------------------------------------------------

	function atualizarCamposPorTipo(tipo) {
		const cartorio = document.getElementById("transparencia-cartorio");
		cartorio.hidden = !TIPOS_COM_CARTORIO.includes(tipo);
	}

	function mostrarArquivoAtual(arquivo) {
		const alvo = document.getElementById("transparencia-arquivo-atual");
		const url = urlDoArquivo(arquivo);
		alvo.hidden = !url;
		alvo.innerHTML = url
			? `Arquivo atual: <a href="${escapeHtml(
					url
			  )}" target="_blank" rel="noopener">${escapeHtml(nomeDoArquivo(arquivo))}</a>`
			: "";
	}

	function abrirDialog(doc) {
		if (!dialogDocumento) return;
		const edicao = Boolean(doc);

		const titulo = document.getElementById("dialog-transparencia-title");
		if (titulo) titulo.textContent = edicao ? "Editar documento" : "Novo documento";

		document.getElementById("transparencia-name").value = edicao ? doc.name : "";
		definirSelect("transparencia-tipo", edicao ? doc.tipo_arquivo : "");
		definirSelect("transparencia-area", edicao ? doc.area : "");
		// Documento novo começa sem data nenhuma.
		definirData("transparencia-emissao", edicao ? doc.data_emissao : "");
		definirData("transparencia-validade", edicao ? doc.data_validade : "");

		const cartorio = switchDe("transparencia-cartorio");
		if (cartorio) cartorio.checked = Boolean(edicao && doc.registrado_em_cartorio);
		const publicado = switchDe("transparencia-publicado");
		if (publicado) publicado.checked = Boolean(edicao && doc.publicado);

		arquivoDoFormulario = edicao ? doc.arquivo : null;
		mostrarArquivoAtual(arquivoDoFormulario);
		const upload = document.getElementById("transparencia-arquivo-upload");
		const rotuloUpload = upload && upload.querySelector(".file-upload__label");
		if (rotuloUpload) rotuloUpload.textContent = edicao ? "Trocar arquivo" : "Arquivo *";
		const mensagemUpload = upload && upload.querySelector("[data-file-upload-message]");
		if (mensagemUpload) mensagemUpload.textContent = "";
		const novo = document.getElementById("transparencia-arquivo-novo");
		novo.hidden = true;
		novo.textContent = "";

		document.getElementById("btn-excluir-transparencia").hidden = !edicao;
		atualizarCamposPorTipo(edicao ? doc.tipo_arquivo : "");
		dialogDocumento.showModal();
	}

	async function salvar(botao) {
		const tipo = valorDoSelect("transparencia-tipo");
		if (!tipo) {
			toast("error", "Escolha o tipo do documento.");
			return;
		}
		if (!arquivoDoFormulario) {
			toast("error", "Envie o arquivo do documento.");
			return;
		}
		const name = document.getElementById("transparencia-name").value;
		const cartorio = switchDe("transparencia-cartorio");
		const publicado = switchDe("transparencia-publicado");
		const dados = {
			name: name || null,
			tipo_arquivo: tipo,
			area: valorDoSelect("transparencia-area"),
			data_emissao: valorDaData("transparencia-emissao"),
			data_validade: valorDaData("transparencia-validade"),
			registrado_em_cartorio: cartorio ? cartorio.checked : false,
			publicado: publicado ? publicado.checked : false,
			arquivo: arquivoDoFormulario,
		};

		botao.disabled = true;
		try {
			const resultado = await chamar(
				"gris.api.administracao.transparencia.salvar_documento_transparencia",
				{ payload: JSON.stringify(dados) }
			);
			documentos = resultado.documentos || documentos;
			renderizar();
			dialogDocumento.close();
			toast("success", name ? "Documento atualizado." : "Documento cadastrado.");
		} catch (erro) {
			toast("error", erro.message);
		} finally {
			botao.disabled = false;
		}
	}

	async function alternarPublicacao(botao) {
		const doc = porName(botao.dataset.name);
		if (!doc) return;
		botao.disabled = true;
		try {
			const resultado = await chamar(
				"gris.api.administracao.transparencia.publicar_documento_transparencia",
				{ name: doc.name, publicado: !doc.publicado }
			);
			documentos = resultado.documentos || documentos;
			renderizar();
			toast("success", doc.publicado ? "Retirado do portal." : "Publicado no portal.");
		} catch (erro) {
			toast("error", erro.message);
			botao.disabled = false;
		}
	}

	function pedirExclusao() {
		const doc = porName(document.getElementById("transparencia-name").value);
		if (!doc || !dialogExclusao) return;
		document.getElementById("transparencia-exclusao-texto").textContent = `${descricaoCurta(
			doc
		)} sai do portal de transparência e o arquivo é apagado. Não dá para desfazer.`;
		dialogExclusao.showModal();
	}

	async function excluir(botao) {
		const name = document.getElementById("transparencia-name").value;
		if (!name) return;
		botao.disabled = true;
		try {
			const resultado = await chamar(
				"gris.api.administracao.transparencia.excluir_documento_transparencia",
				{ name }
			);
			documentos = resultado.documentos || documentos;
			renderizar();
			dialogExclusao.close();
			dialogDocumento.close();
			toast("success", "Documento excluído.");
		} catch (erro) {
			toast("error", erro.message);
		} finally {
			botao.disabled = false;
		}
	}

	// ------------------------------------------------------------------
	// Calendário por cima do dialog
	// ------------------------------------------------------------------
	// O popover do datepicker é `position: absolute` dentro do corpo rolável do dialog,
	// que o cortava. Posicionar por CSS/JS não resolve (já custou três tentativas): o
	// dialog corta tudo o que passa da borda dele. Então o calendário vai para a top layer
	// pela Popover API, acima do próprio dialog, e é posicionado junto do campo — embaixo,
	// ou em cima quando não cabe. O componente continua abrindo e fechando pelo `hidden`.

	const MARGEM_DA_TELA = 8;
	const DISTANCIA_DO_CAMPO = 6;

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

	function sobreporCalendario(raizData) {
		const calendario = raizData.querySelector(".datepicker-popover");
		// Sem Popover API o calendário fica como o componente o desenha.
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

		// Trocar de mês muda a altura; rolar o corpo do dialog ou a janela move o campo.
		const reposicionar = () => aberto() && posicionarCalendario(raizData, calendario);
		new ResizeObserver(reposicionar).observe(calendario);
		dialogDocumento.addEventListener("scroll", reposicionar, true);
		window.addEventListener("resize", reposicionar);
	}

	if (dialogDocumento) {
		dialogDocumento.querySelectorAll("[data-datepicker]").forEach(sobreporCalendario);
		// Fechar o dialog com o calendário aberto não pode deixá-lo sobrando na tela.
		dialogDocumento.addEventListener("close", () => {
			dialogDocumento.querySelectorAll("[data-datepicker]").forEach((raizData) => {
				if (typeof raizData.close === "function") raizData.close();
			});
		});
	}

	// ------------------------------------------------------------------
	// Eventos
	// ------------------------------------------------------------------

	document.getElementById("transparencia-tipo")?.addEventListener("change", function (evento) {
		const valor = evento.detail && evento.detail.value;
		atualizarCamposPorTipo(valor != null ? valor : valorDoSelect("transparencia-tipo"));
	});

	document.addEventListener("gris:file-upload:success", function (evento) {
		if (!evento.target || evento.target.id !== "transparencia-arquivo-upload") return;
		const arquivo = (evento.detail && evento.detail.files && evento.detail.files[0]) || null;
		if (!arquivo || !arquivo.file_url) return;
		arquivoDoFormulario = arquivo.file_url;
		const novo = document.getElementById("transparencia-arquivo-novo");
		novo.textContent = `Arquivo enviado: ${
			arquivo.file_name || nomeDoArquivo(arquivo.file_url)
		}`;
		novo.hidden = false;
	});

	document.getElementById("transparencia-busca")?.addEventListener("input", function (evento) {
		busca = evento.target.value;
		renderizar();
	});

	document.addEventListener("click", function (evento) {
		const cancelar = evento.target.closest("[data-dialog-cancel]");
		if (cancelar) {
			document.getElementById(cancelar.dataset.dialogCancel)?.close();
			return;
		}

		const botaoFiltro = evento.target.closest(".adm-transparencia__filtro [data-filtro]");
		if (botaoFiltro) {
			aplicarFiltro(botaoFiltro.dataset.filtro);
			return;
		}

		const acao = evento.target.closest("[data-acao]");
		if (acao) {
			if (acao.dataset.acao === "novo") abrirDialog(null);
			else if (acao.dataset.acao === "editar") abrirDialog(porName(acao.dataset.name));
			else if (acao.dataset.acao === "publicar") alternarPublicacao(acao);
			return;
		}

		const salvarBtn = evento.target.closest("#btn-salvar-transparencia");
		if (salvarBtn) {
			salvar(salvarBtn);
			return;
		}

		if (evento.target.closest("#btn-excluir-transparencia")) {
			pedirExclusao();
			return;
		}

		const confirmar = evento.target.closest("#btn-confirmar-exclusao");
		if (confirmar) excluir(confirmar);
	});

	renderizar();
})();
