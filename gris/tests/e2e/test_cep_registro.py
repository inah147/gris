"""Validação ponta a ponta do endereço preenchido pelo CEP em `/responsavel/registro`.

Roda contra o site vivo, com navegador de verdade — não entra na suíte do `bench run-tests`,
que não sobe servidor nem browser. Uso:

    cd /workspace/frappe-bench && env/bin/python apps/gris/gris/tests/e2e/test_cep_registro.py

O roteiro cobre o que só se enxerga no navegador: máscara, foco, a cópia para o card com
"Mesmo endereço do jovem", os status de cada desfecho e o guarda de `event.isTrusted` — a
busca por CPF e a cópia de endereço mexem no CEP por código e não podem disparar busca. O
endpoint e o mapeamento da ViaCEP estão cobertos por `gris/tests/test_registro_responsavel.py`.

O caso "encontrado" usa o endpoint e a ViaCEP de verdade, então precisa de rede. Os outros
desfechos são simulados com `page.route` no método do servidor: não dá para pedir à ViaCEP
que caia na hora certa.

O seed cria os dados e o `finally` os remove: `dev.gris` tem dados restaurados de produção e
resíduo de teste ali muda o cenário de quem rodar a suíte depois. Os CPFs são exclusivos
deste arquivo, para não colidir com os dos testes unitários.

Três detalhes deste devcontainer, todos obrigatórios e nenhum óbvio pelo sintoma:

1. `HOME=/workspace`, então o Playwright procura o browser no caminho errado — o
   `executable_path` vai explícito.
2. `dev.gris` não está em `/etc/hosts`; sem `--host-resolver-rules` o `goto` dá `ERR_ABORTED`.
   O bench serve na porta 80.
3. O formulário de `/login` roda no shell do Desk e termina em "Acesso negado": a sessão vem
   do cookie da API, injetado no contexto.

O save de verdade avisa a recepção por WhatsApp. Com a integração ligada no site o roteiro
pula essa etapa, para não mandar mensagem a partir de dados de teste.
"""

import json
import pathlib
import sys
import urllib.request

CHROME = "/workspace/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
BASE = "http://dev.gris"
API = "http://127.0.0.1"
SITE = "dev.gris"

EMAIL = "cep.e2e@example.com"
SENHA = "CepRegistro#E2E1"

METODO = "gris.www.responsavel.registro.buscar_endereco_por_cep"

SHOTS = pathlib.Path(__file__).parent / "shots"

falhas = []


def _cpf(base9: str) -> str:
	"""CPF fictício com dígitos verificadores corretos, a partir de 9 dígitos."""
	digitos = [int(d) for d in base9]
	for posicao in (9, 10):
		soma = sum(d * (posicao + 1 - i) for i, d in enumerate(digitos))
		resto = 11 - (soma % 11)
		digitos.append(0 if resto >= 10 else resto)
	return "".join(str(d) for d in digitos)


NOME_MAE = "Beatriz Nogueira Prado"
NOME_PAI = "Rodrigo Nogueira Prado"
NOME_JOVEM = "Lucas Nogueira Prado"

CPF_MAE = _cpf("314159265")
CPF_PAI = _cpf("271828182")
CPF_JOVEM = _cpf("161803398")

# Endereço de verdade na ViaCEP, usado no caso "encontrado".
CEP_FARIA_LIMA = "04538133"
FARIA_LIMA = {
	"endereco": "Avenida Brigadeiro Faria Lima",
	"bairro": "Itaim Bibi",
	"cidade": "São Paulo",
	"estado": "SP",
}


def checa(rotulo, obtido, esperado):
	ok = obtido == esperado
	print(f"  [{'ok  ' if ok else 'FALHA'}] {rotulo}: {obtido!r}" + ("" if ok else f" != {esperado!r}"))
	if not ok:
		falhas.append(f"{rotulo}: {obtido!r} != {esperado!r}")


# --------------------------------------------------------------------------------------
# Seed e limpeza
# --------------------------------------------------------------------------------------


def _nomes_dos_docs():
	from gris.utils.documento import id_por_cpf

	return {"mae": id_por_cpf(CPF_MAE), "pai": id_por_cpf(CPF_PAI), "jovem": id_por_cpf(CPF_JOVEM)}


def semear():
	import frappe
	from frappe.utils import add_years, nowdate

	frappe.set_user("Administrator")

	if not frappe.db.exists("User", EMAIL):
		user = frappe.new_doc("User")
		user.email = EMAIL
		user.first_name = "CEP E2E"
		user.send_welcome_email = 0
		user.insert(ignore_permissions=True)

	user = frappe.get_doc("User", EMAIL)
	if "Responsavel" not in {r.role for r in user.roles}:
		user.append("roles", {"role": "Responsavel"})
	user.new_password = SENHA
	user.save(ignore_permissions=True)

	def upsert(doctype, cpf, campos):
		from gris.utils.documento import id_por_cpf

		name = id_por_cpf(cpf)
		if frappe.db.exists(doctype, name):
			doc = frappe.get_doc(doctype, name)
			for campo, valor in campos.items():
				doc.set(campo, valor)
			doc.save(ignore_permissions=True)
			return doc.name

		doc = frappe.new_doc(doctype)
		doc.cpf = cpf
		for campo, valor in campos.items():
			doc.set(campo, valor)
		doc.insert(ignore_permissions=True)
		return doc.name

	responsavel_base = {
		"rg": "111111",
		"orgao_expedidor": "SSP",
		"data_de_nascimento": add_years(nowdate(), -38),
		"sexo": "Feminino",
		"estado_civil": "Casado(a)",
		"escolaridade": "Ensino superior completo",
		"cep": "01001-000",
		"endereço": "Rua das Flores",
		"número": 10,
		"bairro": "Centro",
		"cidade": "São Paulo",
		"estado": "SP",
		"celular": "+55 11 99123-4567",
		"profissão": "Engenheira",
		"local_de_trabalho": "Empresa",
	}

	mae = upsert("Responsavel", CPF_MAE, {"nome_completo": NOME_MAE, "email": EMAIL, **responsavel_base})
	# O pai não tem vínculo com o jovem: entra pela busca por CPF. O bairro dele não é o da
	# ViaCEP de propósito — se a busca por CPF disparasse a do CEP, o bairro mudaria.
	pai = upsert(
		"Responsavel",
		CPF_PAI,
		{
			"nome_completo": NOME_PAI,
			"email": "pai.cep.e2e@example.com",
			**responsavel_base,
			"sexo": "Masculino",
			"endereço": "Rua do Cadastro",
			"bairro": "Bairro do Cadastro",
		},
	)

	jovem = upsert(
		"Novo Associado",
		CPF_JOVEM,
		{
			"nome_completo": NOME_JOVEM,
			"data_de_nascimento": add_years(nowdate(), -9),
			"etnia": "Branca",
			"sexo": "Masculino",
			"pais_nascimento": "Brasil",
			"uf_de_nascimento": "SP",
			"cidade_de_nascimento": "Santo André",
			"rg": "222222",
			"orgao_expedidor": "SSP",
			"estado_civil": "Solteiro(a)",
			"religiao": "Não desejo informar",
			"escolaridade": "Ensino fundamental incompleto",
			"cep": "01001-000",
			"endereco": "Rua das Flores",
			"numero": 10,
			"bairro": "Centro",
			"estado": "SP",
			"cidade": "São Paulo",
			"email": "jovem.cep.e2e@example.com",
			"celular": "+55 11 99123-4567",
			"email_cobranca": "cobranca.cep.e2e@example.com",
			"telefone_cobranca": "+55 11 99123-4567",
			# Já enviado: pula a conferência de dupla digitação, que não é o que este roteiro valida.
			"dados_para_registro_enviados": 1,
			"registro_criado_no_paxtu": 0,
		},
	)

	if not frappe.db.exists(
		"Responsavel Vinculo", {"responsavel": mae, "beneficiario_novo_associado": jovem}
	):
		vinculo = frappe.new_doc("Responsavel Vinculo")
		vinculo.responsavel = mae
		vinculo.beneficiario_novo_associado = jovem
		vinculo.set("é_guardiao_legal", 1)
		vinculo.insert(ignore_permissions=True)

	frappe.db.commit()
	return {"mae": mae, "pai": pai, "jovem": jovem}


def limpar():
	import frappe

	frappe.set_user("Administrator")
	nomes = _nomes_dos_docs()

	for name in nomes.values():
		frappe.db.delete("Responsavel Vinculo", {"beneficiario_novo_associado": name})
		frappe.db.delete("Responsavel Vinculo", {"responsavel": name})

	for doctype in ("Novo Associado", "Responsavel"):
		for name in nomes.values():
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)

	if frappe.db.exists("User", EMAIL):
		frappe.delete_doc("User", EMAIL, force=True, ignore_permissions=True)

	frappe.db.commit()


def whatsapp_ligado() -> bool:
	import frappe

	return bool(frappe.db.get_single_value("Configuracoes WhatsApp", "habilitar_integracao"))


# --------------------------------------------------------------------------------------
# Roteiro no navegador
# --------------------------------------------------------------------------------------


def pegar_sid():
	requisicao = urllib.request.Request(
		f"{API}/api/method/login",
		data=json.dumps({"usr": EMAIL, "pwd": SENHA}).encode(),
		headers={"Content-Type": "application/json", "Host": SITE},
	)
	with urllib.request.urlopen(requisicao) as resposta:
		cookies = resposta.headers.get_all("Set-Cookie") or []
	for cookie in cookies:
		if cookie.startswith("sid="):
			return cookie.split(";")[0][4:]
	raise RuntimeError("login não devolveu o cookie de sessão")


# Mesma busca do `findFieldControl` e mesma leitura do `getControlValue` do registro.js: o
# select do Basecoat guarda o valor num input escondido quando o componente não expõe `value`.
# `card` é o índice do card de responsável, ou `null` para os campos do jovem.
LER_CONTROLE = """([card, campo]) => {
	const escopo = card === null
		? document.getElementById("registro-form")
		: document.querySelectorAll(".responsavel-card")[card];
	const fieldScope = card === null ? "main" : "responsavel";
	const control = Array.from(escopo.querySelectorAll("[data-fieldname]")).find(
		(c) => c.dataset.fieldname === campo && c.dataset.fieldScope === fieldScope
	);
	if (!control) return null;
	if (control.classList.contains("select")) {
		return "value" in control
			? control.value || ""
			: control.querySelector(":scope > input[type='hidden']")?.value || "";
	}
	return control.value || "";
}"""

LER_STATUS_CEP = """(id) => {
	const status = document.getElementById(id).closest(".registro-field").querySelector("[data-cep-status]");
	return status.hidden ? "" : status.textContent.trim();
}"""


def _indice_do_card(escopo):
	"""``main`` são os campos do jovem; ``resp-N`` é o N-ésimo card de responsável."""
	return None if escopo == "main" else int(escopo.split("-")[1]) - 1


def valor(page, escopo, campo):
	return page.evaluate(LER_CONTROLE, [_indice_do_card(escopo), campo])


def endereco(page, escopo):
	return {campo: valor(page, escopo, campo) for campo in ("endereco", "bairro", "cidade", "estado")}


def _id_do_cep(escopo):
	return "cep" if escopo == "main" else f"{escopo}-cep"


def cep_input(page, escopo):
	return page.locator(f"#{_id_do_cep(escopo)}")


def status_cep(page, escopo):
	return page.evaluate(LER_STATUS_CEP, _id_do_cep(escopo))


def chama(request, metodo):
	"""A busca de CEP vai por `fetch` a `/api/method/<método>`, mas o `frappe.call` do portal
	(a busca por CPF) posta na raiz do site com o método no corpo (`cmd=...`). Olhar a URL e o
	corpo cobre os dois."""
	return metodo in (request.url + (request.post_data or ""))


def e_busca_cep(request):
	return chama(request, METODO)


def rota_de_chamada(url):
	return url.rstrip("/") == BASE or "/api/method/" in url


def digitar_cep(page, escopo, cep, espera_busca=True):
	"""Digita como uma pessoa (eventos confiáveis) e, se for o caso, espera a resposta."""
	campo = cep_input(page, escopo)
	campo.fill("")
	if espera_busca:
		with page.expect_response(lambda r: e_busca_cep(r.request), timeout=15000):
			campo.press_sequentially(cep, delay=15)
	else:
		campo.press_sequentially(cep, delay=15)
	page.wait_for_timeout(250)


def simular(page, desfecho=None, abortar=False, status=200):
	"""Troca a resposta do endpoint de CEP (até o `desfazer_simulacao`): um desfecho do
	endpoint, um erro HTTP (``desfecho`` vira o corpo do erro) ou uma falha de rede. As outras
	chamadas do portal seguem para o servidor."""
	corpo = {"message": desfecho} if status == 200 else desfecho

	def handler(route):
		if not e_busca_cep(route.request):
			route.continue_()
		elif abortar:
			route.abort()
		else:
			route.fulfill(status=status, content_type="application/json", body=json.dumps(corpo))

	page.route(rota_de_chamada, handler)


def desfazer_simulacao(page):
	page.unroute(rota_de_chamada)


def abrir(page, jovem):
	page.goto(f"{BASE}/responsavel/registro?novo_associado={jovem}")
	page.wait_for_selector("#registro-form")


def cenario_encontrado_e_save(page, docs, buscas, pode_salvar):
	import frappe

	print("\n== CEP encontrado (ViaCEP de verdade), cópia para o card e save ==")
	abrir(page, docs["jovem"])
	page.wait_for_timeout(500)
	checa("abrir a página não dispara busca", len(buscas), 0)

	page.check("#same-address-1")
	checa(
		"CEP do card travado com 'Mesmo endereço'",
		page.eval_on_selector("#resp-1-cep", "el => el.readOnly"),
		True,
	)

	digitar_cep(page, "main", CEP_FARIA_LIMA)
	checa("máscara aplicada", cep_input(page, "main").input_value(), "04538-133")
	checa("endereço do jovem", endereco(page, "main"), FARIA_LIMA)
	checa("foco foi para o número", page.evaluate("document.activeElement.id"), "numero")
	checa(
		"status de sucesso",
		status_cep(page, "main"),
		"Endereço preenchido pelo CEP. Confira e informe o número.",
	)
	checa("card com 'Mesmo endereço' copiou o endereço", endereco(page, "resp-1"), FARIA_LIMA)
	checa("card copiou o CEP", cep_input(page, "resp-1").input_value(), "04538-133")
	checa("uma busca só, sem a do card", len(buscas), 1)
	page.screenshot(path=str(SHOTS / "cep-encontrado.png"), full_page=True)

	# Apagar e redigitar o último dígito devolve o mesmo CEP: não busca de novo.
	cep_input(page, "main").press("End")
	cep_input(page, "main").press("Backspace")
	cep_input(page, "main").press_sequentially("3")
	page.wait_for_timeout(800)
	checa("redigitar o mesmo CEP não busca de novo", len(buscas), 1)

	if not pode_salvar:
		print("  [pula] WhatsApp ligado no site: o save avisaria a recepção de verdade.")
		return

	page.click("#btn-submit-registro")
	if page.locator("#unicoResponsavelDialog").get_attribute("open") is not None:
		page.click("#btn-confirmar-unico-responsavel")
	page.wait_for_selector("#btn-confirm-tipo-registro", state="visible")
	page.click('.registro-option-card[data-value="Definitivo"]')
	page.click("#btn-confirm-tipo-registro")
	page.wait_for_selector("#btn-confirm-save", state="visible")
	resumo = page.inner_text("#confirmation-summary")
	checa("resumo mostra a rua do CEP", FARIA_LIMA["endereco"] in resumo, True)
	page.check("#confirm-data-check")
	page.check("#confirm-image-check")
	page.click("#btn-confirm-save")
	page.wait_for_selector(".toast", timeout=15000)

	# A gravação aconteceu em outra conexão: sem o rollback, esta leria o snapshot antigo.
	frappe.db.rollback()
	gravado = frappe.db.get_value(
		"Novo Associado", docs["jovem"], ["cep", "endereco", "bairro", "cidade", "estado"], as_dict=True
	)
	checa("jovem gravado com o CEP", gravado.cep, "04538-133")
	checa(
		"jovem gravado com o endereço",
		{campo: gravado[campo] for campo in FARIA_LIMA},
		FARIA_LIMA,
	)
	checa(
		"responsável gravado com o endereço copiado",
		frappe.db.get_value("Responsavel", docs["mae"], "endereço"),
		FARIA_LIMA["endereco"],
	)


def cenario_desfechos_simulados(page, docs, buscas):
	print("\n== Desfechos simulados: não encontrado, indisponível, rede e CEP geral ==")
	abrir(page, docs["jovem"])
	antes = endereco(page, "main")

	simular(page, {"encontrado": False, "motivo": "nao_encontrado"})
	digitar_cep(page, "main", "99999999")
	checa(
		"status de CEP não encontrado",
		status_cep(page, "main"),
		"CEP não encontrado. Confira o número ou preencha o endereço manualmente.",
	)
	checa("não encontrado não mexe no endereço", endereco(page, "main"), antes)
	desfazer_simulacao(page)

	neutro = "Não foi possível buscar o endereço agora. Preencha manualmente."
	simular(page, {"encontrado": False, "motivo": "indisponivel"})
	digitar_cep(page, "main", "01310930")
	checa("status com a ViaCEP fora do ar", status_cep(page, "main"), neutro)
	desfazer_simulacao(page)

	simular(page, abortar=True)
	digitar_cep(page, "main", "01310931", espera_busca=False)
	page.wait_for_timeout(800)
	checa("status com falha de rede", status_cep(page, "main"), neutro)
	desfazer_simulacao(page)

	simular(page, {"exc_type": "RateLimitExceededError"}, status=429)
	digitar_cep(page, "main", "01310932")
	checa("status com rate limit (HTTP 429)", status_cep(page, "main"), neutro)
	checa("nenhum diálogo aberto por erro do servidor", page.locator("dialog[open]").count(), 0)
	desfazer_simulacao(page)

	# Endereço renderizado pelo servidor não veio de busca: CEP geral de cidade não o apaga.
	geral = {
		"encontrado": True,
		"motivo": None,
		"endereco": {
			"cep": "35617-000",
			"endereco": "",
			"bairro": "",
			"cidade": "Serra da Saudade",
			"estado": "MG",
		},
	}
	simular(page, geral)
	digitar_cep(page, "main", "35617000")
	checa(
		"CEP geral preserva rua e bairro que não vieram de busca",
		endereco(page, "main"),
		{**antes, "cidade": "Serra da Saudade", "estado": "MG"},
	)
	checa(
		"status do CEP geral", status_cep(page, "main"), "Este CEP é da cidade inteira: informe rua e bairro."
	)
	desfazer_simulacao(page)

	# Agora a rua vem de uma busca: o CEP geral seguinte apaga, e o foco vai para a rua.
	digitar_cep(page, "main", CEP_FARIA_LIMA)
	simular(page, geral)
	digitar_cep(page, "main", "35617000")
	checa("CEP geral apaga a rua que veio de busca", valor(page, "main", "endereco"), "")
	checa("CEP geral apaga o bairro que veio de busca", valor(page, "main", "bairro"), "")
	checa("foco foi para a rua", page.evaluate("document.activeElement.id"), "endereco")

	# Rua digitada à mão deixa de ser da busca: o próximo CEP geral não a apaga.
	page.locator("#endereco").press_sequentially("Rua Digitada", delay=10)
	geral_outro = {**geral, "endereco": {**geral["endereco"], "cep": "35617-001"}}
	desfazer_simulacao(page)
	simular(page, geral_outro)
	digitar_cep(page, "main", "35617001")
	checa("rua digitada à mão sobrevive ao CEP geral", valor(page, "main", "endereco"), "Rua Digitada")
	desfazer_simulacao(page)
	page.screenshot(path=str(SHOTS / "cep-geral.png"), full_page=True)


def cenario_busca_por_cpf(page, docs, buscas):
	print("\n== Busca por CPF não dispara busca de CEP; card busca o próprio CEP ==")
	abrir(page, docs["jovem"])
	page.click("#btn-add-responsavel")
	card = page.locator(".responsavel-card").nth(1)
	card.locator("[data-fieldname='cpf']").fill(CPF_PAI)

	antes = len(buscas)
	with page.expect_response(lambda r: chama(r.request, "buscar_responsavel_por_cpf")):
		card.locator("[data-buscar-cpf]").click()
	page.wait_for_timeout(800)
	checa("busca por CPF não dispara busca de CEP", len(buscas), antes)
	checa("bairro do cadastro preservado", valor(page, "resp-2", "bairro"), "Bairro do Cadastro")
	checa("rua do cadastro preservada", valor(page, "resp-2", "endereco"), "Rua do Cadastro")

	jovem_antes = endereco(page, "main")
	digitar_cep(page, "resp-2", CEP_FARIA_LIMA)
	checa("card do responsável busca o próprio CEP", endereco(page, "resp-2"), FARIA_LIMA)
	checa("foco foi para o número do card", page.evaluate("document.activeElement.id"), "resp-2-numero")
	checa("endereço do jovem não mudou", endereco(page, "main"), jovem_antes)
	page.screenshot(path=str(SHOTS / "cep-card-responsavel.png"), full_page=True)


def rodar_no_navegador(docs, pode_salvar):
	from playwright.sync_api import sync_playwright

	with sync_playwright() as p:
		browser = p.chromium.launch(
			executable_path=CHROME,
			args=["--no-sandbox", f"--host-resolver-rules=MAP {SITE} 127.0.0.1"],
		)
		# O `page.route` não intercepta requisição que passa por service worker (limitação
		# documentada do Playwright), e os desfechos simulados dependem dele: o SW do PWA fica
		# bloqueado. Na vida real ele nem toca na busca, que é um POST.
		contexto = browser.new_context(viewport={"width": 1400, "height": 1000}, service_workers="block")
		contexto.add_cookies([{"name": "sid", "value": pegar_sid(), "domain": SITE, "path": "/"}])
		page = contexto.new_page()
		page.on("pageerror", lambda erro: falhas.append(f"erro de JS na página: {erro}"))
		buscas = []
		page.on("request", lambda req: buscas.append(req.url) if e_busca_cep(req) else None)

		cenario_encontrado_e_save(page, docs, buscas, pode_salvar)
		cenario_desfechos_simulados(page, docs, buscas)
		cenario_busca_por_cpf(page, docs, buscas)

		browser.close()


def main():
	import frappe

	SHOTS.mkdir(parents=True, exist_ok=True)

	frappe.init(site=SITE, sites_path="/workspace/frappe-bench/sites")
	frappe.connect()
	try:
		docs = semear()
		rodar_no_navegador(docs, pode_salvar=not whatsapp_ligado())
	finally:
		limpar()
		frappe.destroy()

	if falhas:
		print("\nFALHOU:\n- " + "\n- ".join(falhas))
		return 1

	print("\nTUDO OK")
	return 0


if __name__ == "__main__":
	sys.exit(main())
