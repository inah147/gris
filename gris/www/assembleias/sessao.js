// Modo sessão: a pauta é a navegação; cada item tem o roteiro da mesa e o registro do
// secretário. Quem edita grava pela fila automática; o presidente só lê e acompanha.
(function () {
	const A = window.grisAssembleias;
	const raiz = document.querySelector(".asm-sessao");
	if (!A || !raiz) return;

	let sessao = A.lerJson(raiz.dataset.sessao, {});
	const editor = !!sessao.pode_editar;
	const estado = { name: sessao.name, modified: sessao.modified };
	let selecionado = sessao.atual;
	let mostrandoGerais = false;
	let seguir = true;

	const RESULTADOS = ["Aprovado por aclamação", "Aprovado", "Reprovado", "Retirado de pauta"];
	const RESULTADOS_DA_CANDIDATURA = ["Eleito", "Suplente", "Não eleito"];
	const CARGOS_DA_ELEICAO = {
		"Eleição da mesa": ["Presidente da mesa", "Secretário da mesa"],
		"Eleição de delegados": ["Delegado"],
		"Eleição da comissão fiscal": ["Comissão Fiscal"],
	};
	const DIRETORIA = "Eleição da diretoria";
	const ASSUNTOS = "Assuntos gerais";
	const EVENTO = "gris_assembleia_sessao";

	const e = A.escapeHtml;
	const itemDe = (nome) => (sessao.itens || []).find((i) => i.name === nome);
	const indiceDe = (nome) => (sessao.itens || []).findIndex((i) => i.name === nome);
	const horaDe = (valor) => String(valor || "").slice(11, 16);

	function agora() {
		const d = new Date();
		const p = (n) => String(n).padStart(2, "0");
		return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(
			d.getMinutes()
		)}:${p(d.getSeconds())}`;
	}

	// ─────────────────────────── Gravação ───────────────────────────

	const indicador = document.querySelector('[data-salvamento="sessao"]');
	let salvamento = null;

	/** Quem edita é dono do que digitou: da resposta vêm os horários, a mesa e o resto. */
	function mesclarDoServidor(novo) {
		if (!editor) {
			sessao = novo;
			return;
		}
		const locais = Object.fromEntries((sessao.itens || []).map((i) => [i.name, i]));
		(novo.itens || []).forEach((i) => {
			const local = locais[i.name];
			if (!local) return;
			["anotacoes", "resultado", "votos_favor", "votos_contra", "votos_abstencao"].forEach(
				(campo) => {
					i[campo] = local[campo];
				}
			);
		});
		novo.anotacoes_gerais = sessao.anotacoes_gerais;
		novo.presentes = sessao.presentes;
		novo.inscricoes = sessao.inscricoes;
		sessao = novo;
	}

	if (editor) {
		salvamento = A.criarSalvamentoAutomatico(estado, {
			metodo: "sessao.salvar_sessao",
			aoSalvar(resposta) {
				mesclarDoServidor(resposta.sessao);
				desenharBarra();
				desenharPauta();
			},
		});
	}
	const salvar = (campos) => salvamento && salvamento.agendar(campos, indicador);

	// ─────────────────────────── Barra da sessão ───────────────────────────

	function desenharBarra() {
		const estadoSessao = document.getElementById("se-estado");
		if (sessao.hora_termino) {
			estadoSessao.className = "asm-sessao__estado";
			estadoSessao.textContent = `Encerrada às ${sessao.hora_termino}`;
		} else if (sessao.aberta_em) {
			estadoSessao.className = "asm-sessao__estado is-ao-vivo";
			estadoSessao.innerHTML = '<i aria-hidden="true"></i>Em sessão';
		} else {
			estadoSessao.className = "asm-sessao__estado";
			estadoSessao.textContent = "Não iniciada";
		}
		document.getElementById("se-inicio").textContent = sessao.hora_inicio || "—";

		const presentes = Number(sessao.presentes) || 0;
		const textoPresentes = document.getElementById("se-presentes-texto");
		if (textoPresentes) textoPresentes.textContent = presentes || "—";
		const quorum = document.getElementById("se-quorum");
		if (!sessao.votantes) {
			quorum.textContent = "lista não gerada";
		} else {
			const atingido = presentes >= sessao.quorum;
			quorum.innerHTML = `${sessao.quorum} de ${sessao.votantes}${
				presentes
					? ` <span class="${
							atingido ? "badge-secondary asm-selo--ok" : "badge-outline"
					  }">${atingido ? "atingido" : "não atingido"}</span>`
					: ""
			}`;
		}

		const presidente = document.getElementById("se-presidente-nome");
		if (presidente) presidente.textContent = sessao.presidente_nome || "a eleger";
		const secretario = document.getElementById("se-secretario-nome");
		if (secretario) secretario.textContent = sessao.secretario_nome || "a eleger";

		const abrir = document.getElementById("se-abrir");
		const encerrar = document.getElementById("se-encerrar");
		if (abrir) abrir.hidden = !!sessao.aberta_em;
		if (encerrar) encerrar.hidden = !sessao.aberta_em || !!sessao.hora_termino;
	}

	// ─────────────────────────── Pauta ───────────────────────────

	function candidaturasDe(cargo) {
		const grupo = ((sessao.inscricoes || {}).cargos || []).find((g) => g.cargo === cargo);
		return (grupo && grupo.candidaturas) || [];
	}

	function resumoDoItem(item) {
		const cargos = CARGOS_DA_ELEICAO[item.finalidade];
		if (cargos) {
			const eleitos = cargos
				.flatMap(candidaturasDe)
				.filter((cand) => cand.resultado === "Eleito")
				.map((cand) => cand.nome.split(" ")[0]);
			return eleitos.length ? `Eleitos: ${eleitos.join(", ")}` : "";
		}
		if (item.finalidade === DIRETORIA) {
			const chapa = ((sessao.inscricoes || {}).chapas || []).find((ch) => ch.eleita);
			return chapa ? `${chapa.titulo} eleita` : "";
		}
		if (!item.resultado) return "";
		const votos = item.votos_favor + item.votos_contra + item.votos_abstencao;
		return votos
			? `${item.resultado} · ${item.votos_favor}×${item.votos_contra}×${item.votos_abstencao}`
			: item.resultado;
	}

	function desenharPauta() {
		const itens = sessao.itens || [];
		const feitos = itens.filter((i) => i.concluido).length;
		document.getElementById(
			"se-progresso"
		).textContent = `Pauta · ${feitos} de ${itens.length}`;
		const linhasGerais = (sessao.anotacoes_gerais || "")
			.split("\n")
			.filter((l) => l.trim()).length;
		document.getElementById("se-itens").innerHTML =
			itens
				.map((item, i) => {
					const atual = item.name === sessao.atual && !item.concluido;
					const estadoItem = item.concluido ? "feito" : atual ? "atual" : "aguarda";
					const resumo = item.concluido
						? resumoDoItem(item)
						: atual && item.iniciado_em
						? "em andamento"
						: "";
					return `<li><button type="button" class="asm-sessao__item" data-item="${e(
						item.name
					)}" data-estado="${estadoItem}"${
						!mostrandoGerais && item.name === selecionado ? ' aria-current="step"' : ""
					}>
						<span class="asm-sessao__marca" aria-hidden="true">${
							item.concluido ? A.icone("check", "xs") : i + 1
						}</span>
						<span class="asm-sessao__item-texto"><span>${e(item.titulo)}</span>${
						resumo ? `<small>${e(resumo)}</small>` : ""
					}</span>
					</button></li>`;
				})
				.join("") +
			`<li class="asm-sessao__gerais"><button type="button" class="asm-sessao__item" data-gerais${
				mostrandoGerais ? ' aria-current="step"' : ""
			}>
				<span class="asm-sessao__marca" aria-hidden="true">${A.icone("notebook-pen", "xs")}</span>
				<span class="asm-sessao__item-texto"><span>Anotações gerais</span><small>${
					linhasGerais
						? `${linhasGerais} ${linhasGerais === 1 ? "linha" : "linhas"}`
						: "fora da pauta"
				}</small></span>
			</button></li>`;
	}

	// ─────────────────────────── Palco ───────────────────────────

	// Rótulo curto no botão; o valor gravado e o title levam o texto inteiro.
	const ROTULO_CURTO = {
		"Aprovado por aclamação": "Aclamação",
		"Retirado de pauta": "Retirado",
	};

	function segmentos(opcoes, atual, atributo, rotulo) {
		return `<div class="asm-segmentos" role="group" aria-label="${e(rotulo)}">${opcoes
			.map(
				(o) =>
					`<button type="button" ${atributo}="${e(o)}" title="${e(o)}" aria-pressed="${
						o === atual
					}">${e(ROTULO_CURTO[o] || o)}</button>`
			)
			.join("")}</div>`;
	}

	function aoVivo(item) {
		const insc = sessao.inscricoes || {};
		if (item.finalidade === "Eleição de delegados") {
			return `<p class="asm-palco__fato"><strong>Vagas:</strong> ${insc.vagas_delegados}</p>`;
		}
		if (item.finalidade === "Eleição da comissão fiscal") {
			return `<p class="asm-palco__fato"><strong>Titulares:</strong> ${insc.titulares_cf} · <strong>Suplentes:</strong> ${insc.suplentes_cf}</p>`;
		}
		if (item.finalidade === ASSUNTOS) {
			const assuntos = insc.assuntos || [];
			return assuntos.length
				? `<ol class="asm-palco__assuntos">${assuntos
						.map(
							(a) =>
								`<li>${e(a.conteudo)} <span class="text-muted-foreground">· ${e(
									a.nome || ""
								)}</span></li>`
						)
						.join("")}</ol>`
				: '<p class="asm-palco__fato">Nenhum assunto enviado pelo formulário.</p>';
		}
		return "";
	}

	function eleicaoHtml(item) {
		const cargos = CARGOS_DA_ELEICAO[item.finalidade];
		if (cargos) {
			return cargos
				.map((cargo) => {
					const lista = candidaturasDe(cargo);
					const linhas = lista.length
						? lista
								.map(
									(cand) => `<li class="asm-eleito">
							<span class="asm-eleito__nome">${e(cand.nome)}${
										cand.registro_ativo
											? ""
											: ' <small class="text-muted-foreground">registro a regularizar</small>'
									}</span>
							${
								editor
									? `<div class="asm-segmentos asm-segmentos--pequeno" role="group" aria-label="Resultado de ${e(
											cand.nome
									  )}">${RESULTADOS_DA_CANDIDATURA.map(
											(r) =>
												`<button type="button" data-candidatura="${e(
													cand.name
												)}" data-res="${e(r)}" aria-pressed="${
													cand.resultado === r
												}">${e(r)}</button>`
									  ).join("")}</div>`
									: `<span class="asm-eleito__resultado">${e(
											cand.resultado || "—"
									  )}</span>`
							}
						</li>`
								)
								.join("")
						: '<li class="asm-palco__fato">Nenhum candidato inscrito. Inscrições na hora entram pela mesa e vão para as anotações.</li>';
					return `<div class="asm-palco__grupo"><h4>${e(
						cargo
					)}</h4><ul class="asm-eleitos">${linhas}</ul></div>`;
				})
				.join("");
		}
		if (item.finalidade === DIRETORIA) {
			const chapas = (sessao.inscricoes || {}).chapas || [];
			if (!chapas.length) {
				return '<p class="asm-palco__fato">Nenhuma chapa inscrita.</p>';
			}
			return `<ul class="asm-eleitos">${chapas
				.map(
					(ch) => `<li class="asm-eleito asm-eleito--chapa">
					<span class="asm-eleito__nome">${e(ch.titulo)}<small class="text-muted-foreground">${(
						ch.membros || []
					)
						.map((m) => `${e(m.funcao)}: ${e(m.nome)}`)
						.join(" · ")}</small></span>
					${
						editor
							? `<button type="button" class="asm-chapa-eleita" data-chapa="${e(
									ch.name
							  )}" aria-pressed="${!!ch.eleita}">${A.icone(
									"check",
									"xs"
							  )}<span>Eleita</span></button>`
							: `<span class="asm-eleito__resultado">${
									ch.eleita ? "Eleita" : "—"
							  }</span>`
					}
				</li>`
				)
				.join("")}</ul>`;
		}
		return "";
	}

	function registroHtml(item) {
		const eleicao = eleicaoHtml(item);
		const partes = [];
		if (eleicao) {
			partes.push(
				`<div class="asm-palco__campo"><span>Resultado da eleição</span>${eleicao}</div>`
			);
		} else if (item.tem_votacao) {
			if (editor) {
				partes.push(`<div class="asm-palco__campo"><span>Resultado</span>${segmentos(
					RESULTADOS,
					item.resultado,
					"data-resultado",
					"Resultado"
				)}</div>
				<div class="asm-palco__votos">
					${[
						["votos_favor", "A favor"],
						["votos_contra", "Contra"],
						["votos_abstencao", "Abstenções"],
					]
						.map(
							([campo, rotulo]) =>
								`<label class="asm-palco__campo"><span>${rotulo}</span><input type="number" min="0" class="input" data-voto="${campo}" value="${
									item[campo] || ""
								}" placeholder="opcional"></label>`
						)
						.join("")}
				</div>`);
			} else {
				const votos = item.votos_favor + item.votos_contra + item.votos_abstencao;
				partes.push(
					`<p class="asm-palco__fato"><strong>Resultado:</strong> ${e(
						item.resultado || "ainda não registrado"
					)}${
						votos
							? ` · ${item.votos_favor} a favor, ${item.votos_contra} contra, ${item.votos_abstencao} abstenções`
							: ""
					}</p>`
				);
			}
		}
		partes.push(
			editor
				? `<label class="asm-palco__campo"><span>Anotações do item</span><textarea class="textarea asm-palco__anotacoes" data-anotacoes rows="7" placeholder="Quem apresentou, perguntas, como foi a votação.">${e(
						item.anotacoes
				  )}</textarea></label>`
				: `<div class="asm-palco__campo"><span>Anotações do secretário</span><p class="asm-palco__texto">${
						e(item.anotacoes) ||
						'<span class="text-muted-foreground">Nada anotado ainda.</span>'
				  }</p></div>`
		);
		return partes.join("");
	}

	function rodapeHtml(item) {
		const i = indiceDe(item.name);
		const anterior = sessao.itens[i - 1];
		const proximo = sessao.itens[i + 1];
		const voltar = anterior
			? `<button type="button" class="btn-ghost" data-ir="${e(anterior.name)}">${A.icone(
					"arrow-left"
			  )}<span>Item ${i}</span></button>`
			: "<span></span>";
		if (!editor) {
			const atual =
				!seguir && sessao.atual && sessao.atual !== item.name
					? `<button type="button" class="btn-outline" data-seguir>Ir para o item atual</button>`
					: "";
			return `${voltar}<div class="asm-acoes">${atual}${
				proximo
					? `<button type="button" class="btn-ghost" data-ir="${e(
							proximo.name
					  )}"><span>Item ${i + 2}</span>${A.icone("arrow-right")}</button>`
					: ""
			}</div>`;
		}
		if (item.concluido) {
			return `${voltar}<div class="asm-acoes">
				<button type="button" class="btn-outline" data-reabrir>Reabrir item</button>
				${
					proximo
						? `<button type="button" class="btn-primary" data-ir="${e(
								proximo.name
						  )}"><span>Ir para o item ${i + 2}</span>${A.icone(
								"arrow-right"
						  )}</button>`
						: ""
				}
			</div>`;
		}
		return `${voltar}<div class="asm-acoes">
			<span class="asm-palco__atalho"><kbd>Ctrl</kbd> <kbd>Enter</kbd></span>
			<button type="button" class="btn-primary" data-concluir><span>${
				proximo ? `Concluir e ir para o item ${i + 2}` : "Concluir o último item"
			}</span>${A.icone(proximo ? "arrow-right" : "check")}</button>
		</div>`;
	}

	function desenharGerais() {
		const palco = document.getElementById("se-palco");
		palco.innerHTML = `<div class="asm-palco__cabeca">
				<h2 class="asm-palco__titulo">Anotações gerais</h2>
				<p class="asm-palco__meta">O que não é de um item da pauta: chegada de pessoas, questão de ordem, intervalo. Entra na ata pelo horário.</p>
			</div>
			${
				editor
					? `<textarea class="textarea asm-palco__anotacoes" data-gerais-texto rows="14" aria-label="Anotações gerais">${e(
							sessao.anotacoes_gerais
					  )}</textarea>`
					: `<p class="asm-palco__texto">${
							e(sessao.anotacoes_gerais) ||
							'<span class="text-muted-foreground">Nada anotado ainda.</span>'
					  }</p>`
			}`;
	}

	function desenharPalco() {
		if (mostrandoGerais) {
			desenharGerais();
			return;
		}
		const palco = document.getElementById("se-palco");
		const item = itemDe(selecionado);
		if (!item) {
			palco.innerHTML = '<p class="asm-palco__fato">A pauta está vazia.</p>';
			return;
		}
		const i = indiceDe(item.name);
		const meta = [
			`Item ${i + 1} de ${sessao.itens.length}`,
			item.tem_votacao ? "Votação" : "",
			item.iniciado_em ? `iniciado às ${horaDe(item.iniciado_em)}` : "",
			item.concluido_em ? `concluído às ${horaDe(item.concluido_em)}` : "",
		]
			.filter(Boolean)
			.join(" · ");
		palco.innerHTML = `<div class="asm-palco__cabeca">
				<h2 class="asm-palco__titulo">${e(item.titulo)}</h2>
				<p class="asm-palco__meta">${e(meta)}</p>
			</div>
			<div class="asm-palco__grade">
				<section class="asm-palco__roteiro" aria-label="Roteiro para a mesa">
					<h3>Roteiro para a mesa</h3>
					<div class="asm-markdown">${item.orientacao_html || ""}</div>
					${aoVivo(item)}
					${
						sessao.orientacoes_gerais_html
							? `<details class="asm-palco__lembretes"><summary>Tipos de votação e lembretes do estatuto</summary><div class="asm-markdown">${sessao.orientacoes_gerais_html}</div></details>`
							: ""
					}
				</section>
				<section class="asm-palco__registro" aria-label="Registro do item">
					<h3>Registro</h3>
					${registroHtml(item)}
				</section>
			</div>
			<div class="asm-palco__rodape">${rodapeHtml(item)}</div>`;
	}

	function desenharTudo() {
		desenharBarra();
		desenharPauta();
		desenharPalco();
	}

	// ─────────────────────────── Ações ───────────────────────────

	function irPara(nome) {
		mostrandoGerais = false;
		selecionado = nome;
		const item = itemDe(nome);
		// Abrir um item ainda não começado, com a sessão aberta, marca o início dele.
		if (editor && item && sessao.aberta_em && !item.iniciado_em && !item.concluido) {
			item.iniciado_em = agora();
			salvar({ itens: { [nome]: { iniciar: 1 } } });
		}
		desenharPauta();
		desenharPalco();
		document.getElementById("se-palco").focus({ preventScroll: true });
	}

	function concluir() {
		const item = itemDe(selecionado);
		if (!item || item.concluido || mostrandoGerais) return;
		const proximo = sessao.itens[indiceDe(item.name) + 1];
		const campos = { itens: { [item.name]: { concluido: 1 } } };
		item.concluido = 1;
		item.concluido_em = agora();
		item.iniciado_em = item.iniciado_em || item.concluido_em;
		if (proximo && sessao.aberta_em && !proximo.iniciado_em && !proximo.concluido) {
			campos.itens[proximo.name] = { iniciar: 1 };
			proximo.iniciado_em = agora();
		}
		salvar(campos);
		sessao.atual = proximo ? proximo.name : item.name;
		if (proximo) selecionado = proximo.name;
		desenharPauta();
		desenharPalco();
		document.getElementById("se-palco").focus({ preventScroll: true });
		window.scrollTo({ top: raiz.offsetTop - 80, behavior: "smooth" });
	}

	raiz.addEventListener("click", (evento) => {
		const alvo = evento.target;
		const item = alvo.closest("[data-item]");
		if (item) {
			if (!editor) {
				seguir = item.dataset.item === sessao.atual;
				const chave = A.switchDe("se-seguir");
				if (chave) chave.checked = seguir;
			}
			irPara(item.dataset.item);
			return;
		}
		if (alvo.closest("[data-gerais]")) {
			mostrandoGerais = true;
			desenharPauta();
			desenharPalco();
			return;
		}
		const ir = alvo.closest("[data-ir]");
		if (ir) {
			irPara(ir.dataset.ir);
			return;
		}
		if (alvo.closest("[data-seguir]")) {
			seguir = true;
			const chave = A.switchDe("se-seguir");
			if (chave) chave.checked = true;
			irPara(sessao.atual);
			return;
		}
		if (!editor) return;
		if (alvo.closest("[data-concluir]")) {
			concluir();
			return;
		}
		if (alvo.closest("[data-reabrir]")) {
			const atual = itemDe(selecionado);
			atual.concluido = 0;
			atual.concluido_em = "";
			salvar({ itens: { [atual.name]: { concluido: 0 } } });
			desenharPauta();
			desenharPalco();
			return;
		}
		const resultado = alvo.closest("[data-resultado]");
		if (resultado) {
			const atual = itemDe(selecionado);
			const valor = resultado.dataset.resultado;
			atual.resultado = atual.resultado === valor ? "" : valor;
			resultado.parentElement.querySelectorAll("[data-resultado]").forEach((b) => {
				b.setAttribute("aria-pressed", String(b.dataset.resultado === atual.resultado));
			});
			salvar({ itens: { [atual.name]: { resultado: atual.resultado } } });
			return;
		}
		const res = alvo.closest("[data-candidatura]");
		if (res) {
			const cand = ((sessao.inscricoes || {}).cargos || [])
				.flatMap((g) => g.candidaturas || [])
				.find((c) => c.name === res.dataset.candidatura);
			if (!cand) return;
			cand.resultado = cand.resultado === res.dataset.res ? "" : res.dataset.res;
			res.parentElement.querySelectorAll("[data-res]").forEach((b) => {
				b.setAttribute("aria-pressed", String(b.dataset.res === cand.resultado));
			});
			salvar({ candidaturas: { [cand.name]: cand.resultado } });
			return;
		}
		const chapa = alvo.closest("[data-chapa]");
		if (chapa) {
			const chapas = (sessao.inscricoes || {}).chapas || [];
			const escolhida = chapas.find((ch) => ch.name === chapa.dataset.chapa);
			const eleita = !escolhida.eleita;
			chapas.forEach((ch) => {
				ch.eleita = ch === escolhida ? eleita : false;
			});
			raiz.querySelectorAll("[data-chapa]").forEach((b) => {
				b.setAttribute(
					"aria-pressed",
					String(chapas.find((ch) => ch.name === b.dataset.chapa).eleita)
				);
			});
			salvar({ chapas: { [escolhida.name]: eleita ? 1 : 0 } });
		}
	});

	raiz.addEventListener("input", (evento) => {
		if (!editor) return;
		const alvo = evento.target;
		if (alvo.matches("[data-anotacoes]")) {
			itemDe(selecionado).anotacoes = alvo.value;
			salvar({ itens: { [selecionado]: { anotacoes: alvo.value } } });
		} else if (alvo.matches("[data-voto]")) {
			const valor = Math.max(parseInt(alvo.value, 10) || 0, 0);
			itemDe(selecionado)[alvo.dataset.voto] = valor;
			salvar({ itens: { [selecionado]: { [alvo.dataset.voto]: valor } } });
		} else if (alvo.matches("[data-gerais-texto]")) {
			sessao.anotacoes_gerais = alvo.value;
			salvar({ ata: { anotacoes_secretario: alvo.value } });
			desenharPauta();
		} else if (alvo.id === "se-presentes") {
			sessao.presentes = Math.max(parseInt(alvo.value, 10) || 0, 0);
			salvar({ ata: { ata_presentes: sessao.presentes } });
			desenharBarra();
		}
	});

	["presidente", "secretario"].forEach((chave) => {
		document.getElementById(`se-${chave}`)?.addEventListener("change", (evento) => {
			const valor = (evento.detail && evento.detail.value) ?? A.valorDoSelect(`se-${chave}`);
			salvar({ ata: { [chave]: valor || "" } });
		});
	});

	document.getElementById("se-abrir")?.addEventListener("click", async () => {
		const primeiro = itemDe(sessao.atual) || (sessao.itens || [])[0];
		const campos = { abrir: 1 };
		if (primeiro && !primeiro.iniciado_em && !primeiro.concluido) {
			campos.itens = { [primeiro.name]: { iniciar: 1 } };
			primeiro.iniciado_em = agora();
		}
		salvar(campos);
		try {
			await salvamento.gravarAgora();
			A.toast("success", "Sessão aberta. O horário de início foi registrado.");
		} catch (erro) {
			A.toast("error", erro.message);
		}
		desenharTudo();
	});

	document.getElementById("se-encerrar")?.addEventListener("click", () => {
		frappe.confirm(
			"Encerrar a sessão agora? O horário de término vai para a ata.",
			async () => {
				salvar({ encerrar: 1 });
				try {
					await salvamento.gravarAgora();
					A.toast("success", "Sessão encerrada.");
				} catch (erro) {
					A.toast("error", erro.message);
				}
				desenharTudo();
			}
		);
	});

	// Anotação geral: fora da pauta, com o horário e o item em andamento.
	const dialogAnotacao = document.getElementById("dialog-anotacao-geral");
	const campoAnotacao = document.getElementById("anotacao-geral-texto");

	function abrirAnotacao() {
		if (!dialogAnotacao) return;
		campoAnotacao.value = "";
		dialogAnotacao.showModal();
		campoAnotacao.focus();
	}

	function anotar() {
		const texto = campoAnotacao.value.trim();
		if (!texto) {
			dialogAnotacao.close();
			return;
		}
		const andamento = itemDe(sessao.atual);
		const contexto = andamento ? ` · durante o item ${indiceDe(andamento.name) + 1}` : "";
		const linha = `- **${agora().slice(11, 16)}${contexto}** ${texto.replace(
			/\s*\n\s*/g,
			" "
		)}`;
		sessao.anotacoes_gerais = sessao.anotacoes_gerais
			? `${sessao.anotacoes_gerais.replace(/\s+$/, "")}\n${linha}`
			: linha;
		salvar({ ata: { anotacoes_secretario: sessao.anotacoes_gerais } });
		dialogAnotacao.close();
		desenharPauta();
		if (mostrandoGerais) desenharPalco();
		A.toast("success", "Anotação registrada.");
	}

	document.getElementById("se-anotar")?.addEventListener("click", abrirAnotacao);
	document.getElementById("btn-anotar")?.addEventListener("click", anotar);
	campoAnotacao?.addEventListener("keydown", (evento) => {
		if (evento.key === "Enter" && !evento.shiftKey) {
			evento.preventDefault();
			anotar();
		}
	});

	document.addEventListener("keydown", (evento) => {
		if (!editor || !(evento.ctrlKey || evento.metaKey)) return;
		if (document.querySelector("dialog[open]")) return;
		if (evento.key === "Enter") {
			evento.preventDefault();
			concluir();
		} else if (evento.key === ".") {
			evento.preventDefault();
			abrirAnotacao();
		}
	});

	// ─────────────────────────── Leitura ao vivo (presidente) ───────────────────────────

	if (!editor) {
		let buscando = false;
		const atualizar = async () => {
			if (buscando || document.hidden) return;
			buscando = true;
			try {
				const resposta = await A.chamar("sessao.ler_sessao", {
					name: sessao.name,
					desde: sessao.modified,
				});
				if (resposta.mudou) {
					sessao = resposta;
					if (seguir && !mostrandoGerais) selecionado = sessao.atual;
					desenharTudo();
				}
			} catch (erro) {
				/* tenta de novo na próxima volta */
			} finally {
				buscando = false;
			}
		};
		setInterval(atualizar, 5000);
		document.addEventListener("visibilitychange", atualizar);
		// Com o socket do Frappe disponível, o aviso chega na hora; sem ele, a consulta resolve.
		try {
			if (window.frappe && frappe.realtime && frappe.realtime.init) {
				frappe.realtime.init();
				frappe.realtime.on(EVENTO, (mensagem) => {
					if (mensagem && mensagem.name === sessao.name) atualizar();
				});
			}
		} catch (erro) {
			/* fica a consulta periódica */
		}
		A.switchDe("se-seguir")?.addEventListener("change", (evento) => {
			seguir = evento.target.checked;
			if (seguir) irPara(sessao.atual);
		});
	}

	desenharTudo();
})();
