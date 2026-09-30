// Formulário da ideia de projeto de captação (nova ou reenviada à Diretoria).
(function () {
	const raiz = document.querySelector(".captacao-ideia");
	if (!raiz || !window.grisCaptacao) return;
	const { chamar, escapeHtml, icone, toast, lerJson } = window.grisCaptacao;

	const projeto = lerJson(raiz.dataset.projeto, {}) || {};
	const listaObjetivos = document.getElementById("ideia-objetivos");

	let objetivos = (projeto.objetivos || []).map((o) => ({
		objetivo: o.objetivo || "",
		metrica_de_sucesso: o.metrica_de_sucesso || "",
	}));
	if (!objetivos.length) objetivos.push({ objetivo: "", metrica_de_sucesso: "" });

	function renderizarObjetivos() {
		listaObjetivos.innerHTML = objetivos
			.map(
				(o, i) => `<div class="captacao-linha" data-indice="${i}">
					<div class="captacao-linha__campos captacao-linha__campos--duplo">
						<textarea class="textarea" rows="2" data-campo="objetivo" placeholder="Objetivo" aria-label="Objetivo ${
							i + 1
						}">${escapeHtml(o.objetivo)}</textarea>
						<input class="input" type="text" data-campo="metrica_de_sucesso" placeholder="Como saber que foi alcançado (opcional)" aria-label="Métrica do objetivo ${
							i + 1
						}" value="${escapeHtml(o.metrica_de_sucesso)}">
					</div>
					<button type="button" class="btn-sm-ghost" data-remover="${i}" aria-label="Remover objetivo ${
					i + 1
				}">${icone("trash-2")}</button>
				</div>`
			)
			.join("");
	}

	function valorDoSelect(id) {
		const elemento = document.getElementById(id);
		const hidden = elemento && elemento.querySelector('input[type="hidden"]');
		return hidden ? hidden.value : "";
	}

	listaObjetivos.addEventListener("input", (evento) => {
		const linha = evento.target.closest("[data-indice]");
		const campo = evento.target.dataset.campo;
		if (!linha || !campo) return;
		objetivos[Number(linha.dataset.indice)][campo] = evento.target.value;
	});

	listaObjetivos.addEventListener("click", (evento) => {
		const remover = evento.target.closest("[data-remover]");
		if (!remover) return;
		objetivos.splice(Number(remover.dataset.remover), 1);
		if (!objetivos.length) objetivos.push({ objetivo: "", metrica_de_sucesso: "" });
		renderizarObjetivos();
	});

	document.getElementById("btn-add-objetivo").addEventListener("click", () => {
		objetivos.push({ objetivo: "", metrica_de_sucesso: "" });
		renderizarObjetivos();
		listaObjetivos.querySelector(".captacao-linha:last-child textarea")?.focus();
	});

	document.getElementById("btn-enviar-ideia").addEventListener("click", async (evento) => {
		const botao = evento.currentTarget;
		const dados = {
			name: projeto.name || "",
			titulo: document.getElementById("ideia-titulo").value.trim(),
			tipo_projeto: valorDoSelect("ideia-tipo"),
			resumo: document.getElementById("ideia-resumo").value.trim(),
			objetivos: objetivos.filter((o) => o.objetivo.trim()),
		};
		if (!dados.titulo || !dados.tipo_projeto || !dados.resumo || !dados.objetivos.length) {
			toast("error", "Preencha título, tipo, resumo e ao menos um objetivo.");
			return;
		}

		botao.disabled = true;
		try {
			const resposta = await chamar("submeter_ideia", { payload: JSON.stringify(dados) });
			toast(
				"success",
				projeto.name ? "Ideia reenviada à Diretoria." : "Ideia enviada à Diretoria."
			);
			window.location.href = `/captacao/projeto?name=${encodeURIComponent(
				resposta.projeto.name
			)}`;
		} catch (erro) {
			toast("error", erro.message);
			botao.disabled = false;
		}
	});

	renderizarObjetivos();
})();
