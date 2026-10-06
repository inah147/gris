// Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
// For license information, please see license.txt

// Árvore de prazos do fluxo de recepção, no formulário "Configuracoes de Recepcao".
// Carregado sob demanda (frappe.require) pelo script do DocType.
//
// O esqueleto (ramos, tipos de registro, etapas e de qual campo sai cada prazo) vem do
// servidor, de `gris.api.recepcao_funil.estrutura_dos_prazos`, a mesma regra do funil. Os
// números saem do próprio formulário, para a árvore acompanhar a edição antes de salvar.

frappe.provide("gris.recepcao_prazos");

gris.recepcao_prazos.escapar = function (valor) {
	return frappe.utils.escape_html(valor === null || valor === undefined ? "" : String(valor));
};

// Mesma leitura de `recepcao_funil._intervalo_da_etapa`: sem `padrao`, é o intervalo geral,
// em que zero vale "mesmo dia"; com `padrao`, zero ou vazio caem nele.
gris.recepcao_prazos.dias = function (doc, campo, padrao) {
	const valor = parseInt(doc[campo], 10);
	if (padrao === null || padrao === undefined) {
		return Number.isFinite(valor) ? valor : 0;
	}
	return Number.isFinite(valor) && valor > 0 ? valor : padrao;
};

gris.recepcao_prazos.rotulo_dias = function (dias) {
	return dias === 1 ? __("1 dia") : __("{0} dias", [dias]);
};

gris.recepcao_prazos.botao_do_campo = function (campo, texto, titulo) {
	const e = gris.recepcao_prazos.escapar;
	return `<button type="button" class="gris-prazos-campo" data-campo="${e(campo)}"
		title="${e(titulo)}">${e(texto)}</button>`;
};

gris.recepcao_prazos.render_nota = function (nota, doc) {
	const e = gris.recepcao_prazos.escapar;
	if (!nota.campo) {
		return `<div class="gris-prazos-nota">${e(nota.texto)}</div>`;
	}

	const dias = gris.recepcao_prazos.dias(doc, nota.campo, nota.padrao);
	const botao = gris.recepcao_prazos.botao_do_campo(
		nota.campo,
		gris.recepcao_prazos.rotulo_dias(dias),
		__("Editar este prazo")
	);
	// O texto é escapado antes de receber o botão: só o botão entra como HTML.
	return `<div class="gris-prazos-nota">${e(nota.texto).replace("{dias}", botao)}</div>`;
};

gris.recepcao_prazos.render_tipo = function (tipo, doc) {
	const e = gris.recepcao_prazos.escapar;
	let dia = 0;

	const itens = tipo.etapas.map((etapa) => {
		const dias = gris.recepcao_prazos.dias(doc, etapa.campo, etapa.padrao);
		dia += dias;

		const intervalo = dias === 0 ? __("mesmo dia") : `+${dias} d`;
		const selo = etapa.proprio_do_ramo
			? `<span class="gris-prazos-selo">${__("prazo próprio")}</span>`
			: "";
		const notas = (etapa.notas || [])
			.map((nota) => gris.recepcao_prazos.render_nota(nota, doc))
			.join("");

		return `
			<li class="gris-prazos-etapa${etapa.proprio_do_ramo ? " gris-prazos-proprio" : ""}">
				<div class="gris-prazos-linha">
					<span class="gris-prazos-rotulo">${e(etapa.label)}</span>
					${selo}
					${gris.recepcao_prazos.botao_do_campo(
						etapa.campo,
						intervalo,
						__("Dias depois da etapa anterior. Clique para editar.")
					)}
					<span class="gris-prazos-dia">${__("dia {0}", [dia])}</span>
				</div>
				${notas}
			</li>`;
	});

	return `
		<li>
			<details open>
				<summary>
					<span class="gris-prazos-rotulo">${e(tipo.rotulo)}</span>
					<span class="gris-prazos-dia">${__("termina no dia {0}", [dia])}</span>
				</summary>
				<ul class="gris-prazos-arvore">${itens.join("")}</ul>
			</details>
		</li>`;
};

gris.recepcao_prazos.render = function (wrapper, estrutura, doc, { ao_clicar } = {}) {
	gris.recepcao_prazos.garantir_estilos();
	const e = gris.recepcao_prazos.escapar;

	const ramos = (estrutura.ramos || []).map(
		(ramo) => `
			<details class="gris-prazos-ramo" open>
				<summary><span class="gris-prazos-rotulo">${e(ramo.rotulo)}</span></summary>
				<ul class="gris-prazos-arvore">
					${ramo.tipos.map((tipo) => gris.recepcao_prazos.render_tipo(tipo, doc)).join("")}
				</ul>
			</details>`
	);

	$(wrapper).html(`
		<div class="gris-prazos">
			<div class="gris-prazos-raiz">
				<span class="gris-prazos-rotulo">${__("Visita realizada")}</span>
				<span class="gris-prazos-dia">${__("dia {0}", [0])}</span>
			</div>
			<div class="gris-prazos-ramos">${ramos.join("")}</div>
		</div>
	`);

	if (ao_clicar) {
		$(wrapper)
			.find(".gris-prazos-campo")
			.on("click", (evento) => ao_clicar($(evento.currentTarget).data("campo")));
	}
};

gris.recepcao_prazos.garantir_estilos = function () {
	if (document.getElementById("gris-recepcao-prazos-estilos")) {
		return;
	}

	const estilos = document.createElement("style");
	estilos.id = "gris-recepcao-prazos-estilos";
	estilos.textContent = `
		.gris-prazos { font-size: 13px; }
		.gris-prazos-raiz { display: flex; align-items: baseline; gap: 8px; font-weight: 600;
			padding: 6px 10px; border: 1px solid var(--border-color); border-radius: var(--border-radius-md);
			background: var(--subtle-fg); width: fit-content; max-width: 100%; }
		.gris-prazos-ramos { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr));
			gap: 12px; margin-top: 12px; }
		.gris-prazos-ramo { border: 1px solid var(--border-color); border-radius: var(--border-radius-md);
			padding: 8px 12px; background: var(--card-bg); min-width: 0; }
		.gris-prazos summary { cursor: pointer; display: flex; flex-wrap: wrap; align-items: baseline;
			gap: 4px 8px; padding: 2px 0; }
		.gris-prazos-ramo > summary { font-weight: 600; }
		.gris-prazos-arvore { list-style: none; margin: 4px 0 0 4px; padding: 0 0 0 14px; }
		.gris-prazos-arvore > li { position: relative; padding: 3px 0 3px 14px; }
		.gris-prazos-arvore > li::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0;
			border-left: 1px solid var(--border-color); }
		.gris-prazos-arvore > li:last-child::before { bottom: auto; height: 14px; }
		.gris-prazos-arvore > li::after { content: ""; position: absolute; left: 0; top: 14px; width: 10px;
			border-top: 1px solid var(--border-color); }
		.gris-prazos-linha { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 8px; }
		.gris-prazos-rotulo { overflow-wrap: anywhere; }
		.gris-prazos-dia { color: var(--text-muted); font-size: 12px; font-variant-numeric: tabular-nums;
			margin-left: auto; white-space: nowrap; }
		.gris-prazos-campo { border: 1px solid var(--border-color); border-radius: var(--border-radius-full);
			background: var(--control-bg); color: var(--text-color); padding: 0 8px; font-size: 12px;
			line-height: 20px; font-variant-numeric: tabular-nums; white-space: nowrap; cursor: pointer; }
		.gris-prazos-campo:hover, .gris-prazos-campo:focus-visible { border-color: var(--text-muted); }
		.gris-prazos-proprio > .gris-prazos-linha .gris-prazos-campo { background: var(--bg-purple);
			color: var(--text-on-purple); border-color: transparent; }
		.gris-prazos-selo { background: var(--bg-purple); color: var(--text-on-purple); font-size: 11px;
			border-radius: var(--border-radius-full); padding: 0 6px; line-height: 18px; white-space: nowrap; }
		.gris-prazos-nota { color: var(--text-muted); font-size: 12px; margin-top: 2px; }
		.gris-prazos-nota .gris-prazos-campo { line-height: 18px; padding: 0 6px; }
		@media (max-width: 640px) {
			.gris-prazos-ramo { padding: 8px; }
			.gris-prazos-arvore { margin-left: 0; padding-left: 6px; }
			.gris-prazos-arvore > li { padding-left: 12px; }
		}
	`;
	document.head.appendChild(estilos);
};
