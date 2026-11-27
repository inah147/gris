// Formulário de candidatura: mesa, delegado, comissão fiscal ou chapa da diretoria.
(function () {
	const A = window.grisAssembleias;
	const raiz = document.querySelector(".asm-formulario-publico");
	const botao = document.getElementById("cand-enviar");
	if (!A || !raiz || !botao) return;

	const assembleia = raiz.dataset.assembleia;
	const chave = raiz.dataset.chave;
	const texto = (id) => (document.getElementById(id)?.value || "").trim();

	function mostrarSucesso(html) {
		document.getElementById("form-candidatura").hidden = true;
		document.getElementById("cand-resumo").innerHTML = html;
		const sucesso = document.getElementById("cand-sucesso");
		sucesso.hidden = false;
		sucesso.scrollIntoView({ behavior: "smooth", block: "start" });
	}

	async function enviarChapa(confirmacao) {
		const membros = Array.from(raiz.querySelectorAll("[data-funcao]")).map((fieldset, i) => ({
			funcao: fieldset.dataset.funcao,
			pessoa: A.valorDoSelect(`membro-${i + 1}`),
			biografia: texto(`membro-${i + 1}-biografia`),
			motivacao: texto(`membro-${i + 1}-motivacao`),
		}));
		if (membros.some((m) => !m.pessoa)) {
			A.toast("error", "Escolha uma pessoa para cada função da chapa.");
			return null;
		}
		return A.chamar("formularios.enviar_chapa", {
			assembleia,
			membros: JSON.stringify(membros),
			confirmacao,
		});
	}

	function cargoEscolhido() {
		const radio = raiz.querySelector('input[name="cargo-mesa"]:checked');
		return radio ? radio.value : botao.dataset.cargoUnico;
	}

	botao.addEventListener("click", async () => {
		const confirmacao = document.getElementById("cand-confirmacao")?.checked ? 1 : 0;
		if (!confirmacao) {
			A.toast("error", "Marque a confirmação para enviar.");
			return;
		}
		botao.disabled = true;
		try {
			if (chave === "diretoria") {
				const resposta = await enviarChapa(confirmacao);
				if (!resposta) return;
				mostrarSucesso(
					`<p class="m-0">A <strong>${A.escapeHtml(
						resposta.titulo
					)}</strong> foi inscrita com:</p><ul>${resposta.membros
						.map(
							([funcao, nome]) =>
								`<li>${A.escapeHtml(funcao)}: <strong>${A.escapeHtml(
									nome
								)}</strong></li>`
						)
						.join("")}</ul>${
						resposta.aviso
							? `<p class="text-muted-foreground">${A.escapeHtml(
									resposta.aviso
							  )}</p>`
							: ""
					}`
				);
				return;
			}
			const cargo = cargoEscolhido();
			if (!cargo) {
				A.toast("error", "Escolha o cargo.");
				return;
			}
			const resposta = await A.chamar("formularios.enviar_candidatura", {
				assembleia,
				cargo,
				confirmacao,
				biografia: texto("cand-biografia"),
				motivacao: texto("cand-motivacao"),
			});
			mostrarSucesso(
				`<p class="m-0"><strong>${A.escapeHtml(
					resposta.nome
				)}</strong> está inscrito(a) para <strong>${A.escapeHtml(
					resposta.cargo
				)}</strong>.</p>${
					resposta.aviso
						? `<p class="text-muted-foreground">${A.escapeHtml(resposta.aviso)}</p>`
						: ""
				}`
			);
		} catch (erro) {
			A.toast("error", erro.message);
		} finally {
			botao.disabled = false;
		}
	});
})();
