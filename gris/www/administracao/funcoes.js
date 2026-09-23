// Catálogo de funções da UEL: tabela e dialog de edição.
(function () {
	const raiz = document.querySelector(".admin-funcoes");
	if (!raiz) return;

	const PODE_EDITAR = raiz.dataset.podeEditar === "1";
	const dialogFuncao = document.getElementById("dialog-funcao");

	let funcoes = lerJson(raiz.dataset.funcoes);
	let responsabilidades = [];

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

	function cabecalhoOrdenavel(rotulo, classe) {
		return `<th${
			classe ? ` class="${classe}"` : ""
		} aria-sort="none" data-sortable><button type="button" class="table-sort-trigger"><span>${rotulo}</span><svg class="ds-lucide ds-lucide--xs table-sort-icon" viewBox="0 0 24 24" aria-hidden="true"><use href="/assets/gris/design_system/icons/lucide/sprite.svg#chevrons-up-down" /></svg></button></th>`;
	}

	/** O switch do design system põe o id no rótulo, não no checkbox. */
	function switchDe(id) {
		const rotulo = document.getElementById(id);
		return rotulo ? rotulo.querySelector('input[type="checkbox"]') : null;
	}

	function toast(categoria, titulo) {
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: { config: { category: categoria, title: titulo, duration: 4500 } },
			})
		);
	}

	function porNome(nome) {
		return funcoes.find((f) => f.name === nome) || null;
	}

	// `frappe.call` no portal engole a mensagem do `frappe.throw`, e é ela que diz
	// por que a gravação foi recusada.
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
			throw new Error(String(mensagem).replace(/<[^>]*>/g, ""));
		}
		return json.message;
	}

	function renderizarTabela() {
		const alvo = document.getElementById("admin-funcoes-tabela");
		if (!alvo) return;

		const linhas = funcoes
			.map((f) => {
				const acoes = PODE_EDITAR
					? `<button type="button" class="btn-sm-ghost" data-acao="detalhes" data-name="${escapeHtml(
							f.name
					  )}" aria-label="Detalhes de ${escapeHtml(f.titulo)}">${icone(
							"ellipsis"
					  )}</button>`
					: "";
				const status = f.ativa
					? '<span class="badge">Ativa</span>'
					: '<span class="badge-outline">Inativa</span>';
				const automatica = f.origem_automatica
					? ' <span class="badge-outline admin-funcoes__auto">automática</span>'
					: "";
				return `<tr>
					<td data-sort-value="${escapeHtml(f.titulo)}">${escapeHtml(f.titulo)}${automatica}</td>
					<td>${escapeHtml(f.categoria || "—")}</td>
					<td data-sort-value="${f.ativa ? 1 : 0}">${status}</td>
					<td class="admin-funcoes__numero">${f.pessoas}</td>
					<td class="admin-funcoes__acoes">${acoes}</td>
				</tr>`;
			})
			.join("");

		alvo.innerHTML = `<table class="table table-sortable admin-funcoes__tabela" data-table-sortable>
			<thead>
				<tr>
					${cabecalhoOrdenavel("Título")}
					${cabecalhoOrdenavel("Linha")}
					${cabecalhoOrdenavel("Status")}
					${cabecalhoOrdenavel("Pessoas", "admin-funcoes__numero")}
					<th class="admin-funcoes__acoes"></th>
				</tr>
			</thead>
			<tbody>${linhas}</tbody>
		</table>`;
	}

	function renderizarResponsabilidades() {
		const corpo = document.getElementById("funcao-responsabilidades-corpo");
		if (!corpo) return;
		if (!responsabilidades.length) {
			corpo.innerHTML =
				'<tr><td colspan="3" class="text-muted-foreground text-sm">Nenhuma responsabilidade cadastrada.</td></tr>';
			return;
		}
		corpo.innerHTML = responsabilidades
			.map(
				(r, indice) => `<tr>
					<td>${escapeHtml(r.responsabilidade)}</td>
					<td>${escapeHtml(r.detalhe || "—")}</td>
					<td class="admin-dialog__acoes">
						<button type="button" class="btn-sm-ghost" data-acao="remover-responsabilidade" data-indice="${indice}">Remover</button>
					</td>
				</tr>`
			)
			.join("");
	}

	function definirComponente(id, valor) {
		// O select expõe `value` na raiz; escrever no hidden não atualizaria o rótulo.
		const elemento = document.getElementById(id);
		if (elemento) elemento.value = valor || "";
	}

	function valorDoSelect(id) {
		const elemento = document.getElementById(id);
		if (!elemento) return "";
		const hidden = elemento.querySelector('input[type="hidden"]');
		return hidden ? hidden.value : "";
	}

	function abrirDialog(funcao) {
		if (!dialogFuncao) return;
		const nova = !funcao;
		const automatica = !nova && funcao.origem_automatica;

		document.getElementById("funcao-name").value = nova ? "" : funcao.name;
		const titulo = document.getElementById("funcao-titulo");
		titulo.value = nova ? "" : funcao.titulo;
		// A sincronização de seções reconhece a função pelo título exato: renomear
		// uma função automática quebraria a rotina em silêncio.
		titulo.disabled = automatica;
		document.getElementById("funcao-descricao").value = nova ? "" : funcao.descricao || "";
		const ativa = switchDe("funcao-ativa");
		if (ativa) ativa.checked = nova ? true : funcao.ativa;
		definirComponente("funcao-linha", nova ? "" : funcao.categoria || "");

		const aviso = document.getElementById("funcao-aviso-automatica");
		if (aviso) aviso.hidden = !automatica;

		responsabilidades = nova ? [] : funcao.responsabilidades.map((r) => ({ ...r }));
		renderizarResponsabilidades();

		document.getElementById("funcao-nova-responsabilidade").value = "";
		document.getElementById("funcao-novo-detalhe").value = "";
		dialogFuncao.showModal();
	}

	async function salvar(botao) {
		const ativa = switchDe("funcao-ativa");
		const payload = {
			name: document.getElementById("funcao-name").value,
			titulo: document.getElementById("funcao-titulo").value.trim(),
			categoria: valorDoSelect("funcao-linha"),
			descricao: document.getElementById("funcao-descricao").value.trim(),
			ativa: ativa ? ativa.checked : true,
			responsabilidades: responsabilidades,
		};
		if (!payload.titulo) {
			toast("error", "Informe o título da função.");
			return;
		}

		botao.disabled = true;
		try {
			const resultado = await chamar("gris.api.administracao.salvar_funcao", payload);
			if (resultado && resultado.funcoes) {
				funcoes = resultado.funcoes;
				renderizarTabela();
			}
			dialogFuncao.close();
			toast("success", payload.name ? "Função atualizada." : "Função criada.");
		} catch (erro) {
			toast("error", erro.message);
		} finally {
			botao.disabled = false;
		}
	}

	document.addEventListener("click", function (evento) {
		const cancelar = evento.target.closest("[data-dialog-cancel]");
		if (cancelar) {
			document.getElementById(cancelar.dataset.dialogCancel)?.close();
			return;
		}

		if (evento.target.closest("#btn-nova-funcao")) {
			abrirDialog(null);
			return;
		}

		const salvarBtn = evento.target.closest("#btn-salvar-funcao");
		if (salvarBtn) {
			salvar(salvarBtn);
			return;
		}

		if (evento.target.closest("#btn-add-responsabilidade")) {
			const campo = document.getElementById("funcao-nova-responsabilidade");
			const detalhe = document.getElementById("funcao-novo-detalhe");
			const texto = campo.value.trim();
			if (!texto) {
				toast("error", "Escreva a responsabilidade.");
				return;
			}
			responsabilidades.push({ responsabilidade: texto, detalhe: detalhe.value.trim() });
			campo.value = "";
			detalhe.value = "";
			renderizarResponsabilidades();
			return;
		}

		const acao = evento.target.closest("[data-acao]");
		if (!acao) return;

		if (acao.dataset.acao === "detalhes") {
			abrirDialog(porNome(acao.dataset.name));
		} else if (acao.dataset.acao === "remover-responsabilidade") {
			responsabilidades.splice(Number(acao.dataset.indice), 1);
			renderizarResponsabilidades();
		}
	});

	renderizarTabela();
})();
