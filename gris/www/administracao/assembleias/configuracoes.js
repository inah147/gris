// Configurações de assembleias: pautas padrão, materiais e a gravação de tudo.
(function () {
	const A = window.grisAssembleias;
	const raiz = document.querySelector(".asm-config");
	if (!A || !raiz) return;

	const dados = A.lerJson(raiz.dataset.config, {});
	const orientacaoPadrao = (finalidade) =>
		(dados.orientacoes || {})[finalidade] || dados.orientacao_simples || "";

	const editores = {};
	raiz.querySelectorAll("[data-pauta]").forEach((container) => {
		const chave = container.dataset.pauta;
		editores[chave] = A.criarEditorDePauta(container, dados[chave] || [], {
			finalidades: dados.finalidades,
			orientacaoPadrao,
		});
	});
	raiz.addEventListener("click", (evento) => {
		const botao = evento.target.closest("[data-adicionar-item]");
		if (botao) editores[botao.dataset.adicionarItem]?.adicionar();
	});

	// ── Materiais ──
	let materiais = (dados.materiais || []).slice();
	const listaMateriais = document.getElementById("cfg-materiais");

	function desenharMateriais() {
		listaMateriais.innerHTML = materiais
			.map(
				(item, i) =>
					`<li><span class="badge-outline">${A.escapeHtml(
						item
					)}<button type="button" class="btn-sm-ghost" data-remover-material="${i}" aria-label="Remover ${A.escapeHtml(
						item
					)}">${A.icone("x", "xs")}</button></span></li>`
			)
			.join("");
	}
	desenharMateriais();

	listaMateriais.addEventListener("click", (evento) => {
		const botao = evento.target.closest("[data-remover-material]");
		if (!botao) return;
		materiais.splice(Number(botao.dataset.removerMaterial), 1);
		desenharMateriais();
	});

	function adicionarMaterial() {
		const campo = document.getElementById("cfg-novo-material");
		const valor = campo.value.trim();
		if (!valor) return;
		materiais.push(valor);
		campo.value = "";
		desenharMateriais();
		campo.focus();
	}
	document.getElementById("cfg-adicionar-material").addEventListener("click", adicionarMaterial);
	document.getElementById("cfg-novo-material").addEventListener("keydown", (evento) => {
		if (evento.key === "Enter") {
			evento.preventDefault();
			adicionarMaterial();
		}
	});

	// ── Gravação ──
	const valor = (id) => (document.getElementById(id)?.value || "").trim();
	const inteiro = (id) => parseInt(valor(id), 10) || 0;
	const ligado = (id) => (A.switchDe(id)?.checked ? 1 : 0);

	function coletar() {
		const payload = {
			dias_limite_edital: inteiro("cfg-dias-limite"),
			local_padrao: valor("cfg-local"),
			cidade: valor("cfg-cidade"),
			grupo_diretoria_whatsapp: A.valorDoSelect("cfg-grupo"),
			texto_topo_edital: valor("cfg-topo"),
			texto_rodape_edital: valor("cfg-rodape"),
			orientacoes_gerais: valor("cfg-orientacoes"),
			voto_escotistas: ligado("cfg-voto-escotistas"),
			voto_dirigentes: ligado("cfg-voto-dirigentes"),
			voto_demais_associados: ligado("cfg-voto-demais"),
			exigir_registro_ativo: ligado("cfg-registro-ativo"),
			voto_jovens: ligado("cfg-voto-jovens"),
			idade_minima_voto_jovem: inteiro("cfg-idade-voto"),
			voto_representado_por_responsavel: ligado("cfg-representacao"),
			// Na tela em anos (6,5); no banco em meses, para não depender de float.
			idade_minima_representacao_meses: Math.round(
				(parseFloat(valor("cfg-idade-representacao").replace(",", ".")) || 0) * 12
			),
			voto_por_matilha: ligado("cfg-matilha"),
			voto_por_patrulha_escoteiro: ligado("cfg-patrulha-escoteiro"),
			voto_por_patrulha_senior: ligado("cfg-patrulha-senior"),
			manter_aberto_sem_candidatos: ligado("cfg-manter-aberto"),
			vagas_comissao_fiscal: inteiro("cfg-vagas-cf"),
			suplentes_comissao_fiscal: inteiro("cfg-suplentes-cf"),
			associados_por_delegado: inteiro("cfg-por-delegado"),
			modelo_ata: valor("cfg-modelo-ata"),
			pauta_ordinaria: editores.pauta_ordinaria.itens(),
			pauta_extraordinaria: editores.pauta_extraordinaria.itens(),
			materiais,
		};
		["mesa", "diretoria", "comissao_fiscal", "delegado", "assuntos_gerais"].forEach(
			(chave) => {
				payload[`prazo_${chave}_unidade`] =
					A.valorDoSelect(`cfg-prazo-${chave}-unidade`) || "Sem limite";
				payload[`prazo_${chave}_valor`] = inteiro(`cfg-prazo-${chave}-valor`);
			}
		);
		return payload;
	}

	document.getElementById("cfg-salvar").addEventListener("click", async (evento) => {
		const botao = evento.currentTarget;
		botao.disabled = true;
		try {
			await A.chamar("endpoints.salvar_configuracoes", {
				payload: JSON.stringify(coletar()),
			});
			A.toast("success", "Configurações salvas.");
		} catch (erro) {
			A.toast("error", erro.message);
		} finally {
			botao.disabled = false;
		}
	});
})();
