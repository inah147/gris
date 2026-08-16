(function () {
	const raiz = document.querySelector(".insignias-catalogo");
	if (!raiz) return;

	const dialogItem = document.getElementById("dialog-item");
	const campoName = document.getElementById("item-name");
	const wrapperNome = document.getElementById("item-nome-wrapper");
	const avisoNome = document.getElementById("item-nome-fixo");

	function showToast(category, message) {
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: { config: { category, title: message, duration: 3500 } },
			})
		);
	}

	function lerValor(nome) {
		const campo = dialogItem.querySelector(`[name="${nome}"]`);
		return campo ? (campo.value || "").trim() : "";
	}

	function definirCampo(nome, valor) {
		const campo = dialogItem.querySelector(`[name="${nome}"]`);
		if (campo) campo.value = valor;
	}

	// Select e currency-input expõem `value` no elemento raiz; escrever no hidden
	// input direto não atualizaria o rótulo visível do componente.
	function definirComponente(id, valor) {
		const root = document.getElementById(id);
		if (root) root.value = valor;
	}

	function abrirDialog(modo, dados) {
		const novo = modo === "novo";
		campoName.value = novo ? "" : dados.name;
		wrapperNome.hidden = !novo;
		avisoNome.hidden = novo;

		definirCampo("nome", novo ? "" : dados.nome);
		definirComponente("item-tipo", novo ? "Distintivo de Progressão" : dados.tipo);
		definirComponente("item-ramo", novo ? "Todos" : dados.ramo);
		definirComponente("item-valor", novo ? "" : Number(dados.valor || 0));
		definirCampo("codigo", novo ? "" : dados.codigo);
		definirCampo("descricao", novo ? "" : dados.descricao);

		dialogItem.showModal();
	}

	document.getElementById("btn-novo-item")?.addEventListener("click", function () {
		abrirDialog("novo");
	});

	raiz.addEventListener("click", function (event) {
		const cancelar = event.target.closest("[data-dialog-cancel]");
		if (cancelar) {
			document.getElementById(cancelar.dataset.dialogCancel)?.close();
			return;
		}

		const botao = event.target.closest("[data-acao]");
		if (!botao) return;

		if (botao.dataset.acao === "editar") {
			abrirDialog("editar", {
				name: botao.dataset.name,
				nome: botao.dataset.nome,
				tipo: botao.dataset.tipo,
				ramo: botao.dataset.ramo,
				codigo: botao.dataset.codigo,
				valor: botao.dataset.valor,
				descricao: botao.dataset.descricao,
			});
			return;
		}

		if (botao.dataset.acao === "alternar") {
			botao.disabled = true;
			frappe.call({
				method: "gris.api.insignias.endpoints.alternar_item_catalogo",
				args: { payload: JSON.stringify({ name: botao.dataset.name }) },
				freeze: true,
				freeze_message: "Salvando...",
				callback: function (r) {
					if (r.exc || !r.message) return;
					showToast("success", r.message.ativo ? "Item reativado." : "Item inativado.");
					window.location.reload();
				},
				always: function () {
					botao.disabled = false;
				},
			});
		}
	});

	document.getElementById("btn-salvar-item")?.addEventListener("click", function () {
		const name = campoName.value;
		const nome = lerValor("nome");

		if (!name && nome.length < 3) {
			showToast("warning", "Informe um nome com pelo menos 3 caracteres.");
			return;
		}
		if (!lerValor("tipo")) {
			showToast("warning", "Selecione o tipo do item.");
			return;
		}
		if (!lerValor("ramo")) {
			showToast("warning", "Selecione o ramo do item.");
			return;
		}

		const payload = {
			tipo: lerValor("tipo"),
			ramo: lerValor("ramo"),
			valor_unitario: lerValor("valor_unitario") || 0,
			codigo: lerValor("codigo"),
			descricao: lerValor("descricao"),
		};
		if (name) {
			payload.name = name;
		} else {
			payload.nome = nome;
		}

		this.disabled = true;
		frappe.call({
			method: "gris.api.insignias.endpoints.salvar_item_catalogo",
			args: { payload: JSON.stringify(payload) },
			freeze: true,
			freeze_message: "Salvando...",
			callback: function (r) {
				if (r.exc || !r.message) return;
				showToast("success", r.message.criado ? "Item cadastrado." : "Item atualizado.");
				window.location.reload();
			},
			always: () => {
				this.disabled = false;
			},
		});
	});
})();
