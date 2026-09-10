"""Validação ponta a ponta do switch de carteirinha em `/responsavel/registro`.

Roda contra o site vivo, com navegador de verdade — não entra na suíte do `bench run-tests`,
que não sobe servidor nem browser. Uso:

    cd /workspace/frappe-bench && env/bin/python apps/gris/gris/tests/e2e/test_carteirinha_registro.py

O roteiro cobre o que só se enxerga no navegador: o total reagindo ao tipo de registro e a
cada switch, um switch por pessoa registrada no ramo Filhotes, e a escolha chegando à ficha
da recepção como badge. As regras de gravação em si estão cobertas por
`gris/tests/test_registro_responsavel.py` e `gris/tests/test_registro_filhotes.py`.

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
"""

import json
import pathlib
import sys
import urllib.request

CHROME = "/workspace/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
BASE = "http://dev.gris"
API = "http://127.0.0.1"
SITE = "dev.gris"

EMAIL = "carteirinha.e2e@example.com"
SENHA = "Carteirinha#E2E1"

VALOR_PROVISORIO = 50.0
VALOR_DEFINITIVO = 150.0
VALOR_CARTEIRINHA = 25.0

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


NOME_MAE = "Ana Paula Ribeiro Alves"
NOME_PAI = "Carlos Eduardo Ribeiro Alves"
NOME_LOBINHO = "Miguel Ribeiro Alves"
NOME_FILHOTE = "Helena Ribeiro Alves"

CPF_MAE = _cpf("777111444")
CPF_PAI = _cpf("982247529")
CPF_LOBINHO = _cpf("533447390")
CPF_FILHOTE = _cpf("995350168")


def checa(rotulo, obtido, esperado):
	ok = obtido == esperado
	print(f"  [{'ok  ' if ok else 'FALHA'}] {rotulo}: {obtido!r}" + ("" if ok else f" != {esperado!r}"))
	if not ok:
		falhas.append(f"{rotulo}: {obtido!r} != {esperado!r}")


def brl(valor: float) -> str:
	formatado = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
	return f"R$ {formatado}"


# --------------------------------------------------------------------------------------
# Seed e limpeza
# --------------------------------------------------------------------------------------


def _nomes_dos_docs():
	from gris.utils.documento import id_por_cpf

	return {
		"mae": id_por_cpf(CPF_MAE),
		"pai": id_por_cpf(CPF_PAI),
		"lobinho": id_por_cpf(CPF_LOBINHO),
		"filhote": id_por_cpf(CPF_FILHOTE),
	}


def semear():
	import frappe
	from frappe.utils import add_years, nowdate

	frappe.set_user("Administrator")

	# Os valores do diálogo ficam fixos para o total ser conferível.
	for campo, valor in (
		("valor_registro_provisorio", VALOR_PROVISORIO),
		("valor_registro_definitivo", VALOR_DEFINITIVO),
		("valor_carteirinha", VALOR_CARTEIRINHA),
	):
		frappe.db.set_single_value("Configuracoes de Recepcao", campo, valor)

	vagas = frappe.get_single("Vagas")
	vagas.idade_transicao_filhotes = 6.5
	vagas.save(ignore_permissions=True)

	if not frappe.db.exists("User", EMAIL):
		user = frappe.new_doc("User")
		user.email = EMAIL
		user.first_name = "Carteirinha E2E"
		user.send_welcome_email = 0
		user.insert(ignore_permissions=True)

	# `Recepcao` entra junto porque o mesmo roteiro confere a ficha da recepção no fim.
	user = frappe.get_doc("User", EMAIL)
	papeis = {r.role for r in user.roles}
	for papel in ("Responsavel", "Recepcao"):
		if papel not in papeis:
			user.append("roles", {"role": papel})
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
		"cidade_de_nascimento": "Santo André",
		"uf_de_nascimento": "SP",
		"cep": "01001-000",
		"bairro": "Centro",
		"cidade": "São Paulo",
		"estado": "SP",
		"celular": "+55 11 99123-4567",
		"endereço": "Rua das Flores",
		"número": 10,
		"profissão": "Engenheira",
		"local_de_trabalho": "Empresa",
		# O ramo Filhotes exige documento com foto de quem será registrado, no cliente e no
		# servidor: sem isto o submit nem chega ao diálogo do tipo de registro.
		"link_documento_identificacao": "https://drive.example/e2e-documento",
		"link_declaracao_idoneidade_assinada": "https://drive.example/e2e-declaracao",
	}

	mae = upsert("Responsavel", CPF_MAE, {"nome_completo": NOME_MAE, "email": EMAIL, **responsavel_base})
	pai = upsert(
		"Responsavel",
		CPF_PAI,
		{
			"nome_completo": NOME_PAI,
			"email": "pai.carteirinha.e2e@example.com",
			**responsavel_base,
			"sexo": "Masculino",
		},
	)

	jovem_base = {
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
		"email": "jovem.carteirinha.e2e@example.com",
		"celular": "+55 11 99123-4567",
		"email_cobranca": "cobranca.carteirinha.e2e@example.com",
		"telefone_cobranca": "+55 11 99123-4567",
		# Já enviado: pula a conferência de dupla digitação, que não é o que este roteiro valida.
		"dados_para_registro_enviados": 1,
		"registro_criado_no_paxtu": 0,
	}

	lobinho = upsert(
		"Novo Associado",
		CPF_LOBINHO,
		{
			"nome_completo": NOME_LOBINHO,
			"data_de_nascimento": add_years(nowdate(), -9),
			**jovem_base,
		},
	)
	filhote = upsert(
		"Novo Associado",
		CPF_FILHOTE,
		{
			"nome_completo": NOME_FILHOTE,
			"data_de_nascimento": add_years(nowdate(), -5),
			**jovem_base,
			"sexo": "Feminino",
		},
	)

	def vincular(responsavel, jovem, sera_registrado):
		name = frappe.db.get_value(
			"Responsavel Vinculo",
			{"responsavel": responsavel, "beneficiario_novo_associado": jovem},
			"name",
		)
		if name:
			doc = frappe.get_doc("Responsavel Vinculo", name)
		else:
			doc = frappe.new_doc("Responsavel Vinculo")
			doc.responsavel = responsavel
			doc.beneficiario_novo_associado = jovem
		doc.sera_registrado = sera_registrado
		doc.set("é_guardiao_legal", 1)
		doc.save(ignore_permissions=True)

	# Lobinho: nenhum responsável registrado -> só o switch do jovem.
	vincular(mae, lobinho, 0)
	# Filhotes: os dois registrados -> um switch para cada, além do jovem.
	vincular(mae, filhote, 1)
	vincular(pai, filhote, 1)

	frappe.db.commit()
	return {"mae": mae, "pai": pai, "lobinho": lobinho, "filhote": filhote}


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


def total(page):
	return page.inner_text("#registro-total-valor").strip()


def switches_de_responsavel(page):
	return page.locator(".registro-carteirinha__switch[data-carteirinha='responsavel']:visible")


def abrir_dialogo(page, novo_associado, passo):
	page.goto(f"{BASE}/responsavel/registro?novo_associado={novo_associado}")
	page.wait_for_selector("#registro-form")

	# No ramo Filhotes a página abre sozinha o diálogo da declaração de idoneidade, que cobre
	# o botão de salvar. Ele não faz parte deste roteiro.
	for _ in range(3):
		if page.locator("dialog[open]").count() == 0:
			break
		page.keyboard.press("Escape")
		page.wait_for_timeout(300)

	page.click("#btn-submit-registro")

	# Com um responsável só, a confirmação vem antes do diálogo do tipo de registro. Um
	# <dialog> aberto reporta altura 0 ao Playwright, então o estado se lê pelo atributo
	# `open` e as esperas acontecem nos filhos, que têm caixa de verdade.
	if page.locator("#unicoResponsavelDialog").get_attribute("open") is not None:
		page.click("#btn-confirmar-unico-responsavel")

	page.wait_for_selector("#btn-confirm-tipo-registro", state="visible")
	# O diálogo tem transição de abertura: sem esperar, a screenshot sai meio transparente.
	page.wait_for_timeout(400)
	page.screenshot(path=str(SHOTS / f"{passo}-dialogo.png"))


def confirmar_e_salvar(page, passo):
	page.click("#btn-confirm-tipo-registro")
	page.wait_for_selector("#btn-confirm-save", state="visible")
	page.check("#confirm-data-check")
	page.check("#confirm-image-check")
	page.click("#btn-confirm-save")
	page.wait_for_selector(".toast", timeout=15000)
	page.screenshot(path=str(SHOTS / f"{passo}-salvo.png"))


def cenario_lobinho(page, docs):
	print("\n== Diálogo, ramo Lobinho (só o jovem é registrado) ==")
	abrir_dialogo(page, docs["lobinho"], "lobinho")

	checa("switch do jovem visível", page.locator("#carteirinha-jovem").is_visible(), True)
	checa("switch do jovem ligado por padrão", page.locator("#carteirinha-jovem input").is_checked(), True)
	checa(
		"rótulo do jovem traz o nome",
		page.locator("#carteirinha-jovem span").inner_text().strip(),
		f"Quero a carteirinha física de {NOME_LOBINHO}",
	)
	checa("nenhum switch de responsável", switches_de_responsavel(page).count(), 0)
	checa("total antes de escolher o tipo", total(page), "—")

	page.click('.registro-option-card[data-value="Provisório"]')
	checa("provisório + carteirinha", total(page), brl(VALOR_PROVISORIO + VALOR_CARTEIRINHA))
	page.screenshot(path=str(SHOTS / "lobinho-provisorio.png"))

	page.uncheck("#carteirinha-jovem input")
	checa("provisório sem carteirinha", total(page), brl(VALOR_PROVISORIO))
	page.wait_for_timeout(300)
	page.screenshot(path=str(SHOTS / "lobinho-sem-carteirinha.png"))

	page.check("#carteirinha-jovem input")
	page.click('.registro-option-card[data-value="Definitivo"]')
	checa("definitivo + carteirinha", total(page), brl(VALOR_DEFINITIVO + VALOR_CARTEIRINHA))

	# Salva recusando: é assim que se confere que o 0 vence o default 1 do schema.
	page.uncheck("#carteirinha-jovem input")
	checa("definitivo sem carteirinha", total(page), brl(VALOR_DEFINITIVO))
	confirmar_e_salvar(page, "lobinho")


def cenario_filhotes(page, docs):
	print("\n== Diálogo, ramo Filhotes (jovem + 2 responsáveis registrados) ==")
	abrir_dialogo(page, docs["filhote"], "filhotes")

	checa("um switch por responsável registrado", switches_de_responsavel(page).count(), 2)
	checa(
		"rótulo do jovem traz o nome",
		page.locator("#carteirinha-jovem span").inner_text().strip(),
		f"Quero a carteirinha física de {NOME_FILHOTE}",
	)
	checa(
		"provisório indisponível no ramo",
		page.locator('.registro-option-card[data-value="Provisório"]').is_hidden(),
		True,
	)
	checa(
		"rótulos nomeiam cada responsável",
		sorted(switches_de_responsavel(page).locator("span").all_inner_texts()),
		[f"Quero a carteirinha física de {NOME_MAE}", f"Quero a carteirinha física de {NOME_PAI}"],
	)

	# Definitivo entra pré-selecionado no ramo: 3 registros + 3 carteirinhas.
	checa("total com todas as carteirinhas", total(page), brl(3 * VALOR_DEFINITIVO + 3 * VALOR_CARTEIRINHA))
	page.screenshot(path=str(SHOTS / "filhotes-todas.png"))

	page.uncheck("#carteirinha-resp-2 input")
	checa("uma carteirinha a menos", total(page), brl(3 * VALOR_DEFINITIVO + 2 * VALOR_CARTEIRINHA))
	page.wait_for_timeout(300)
	page.screenshot(path=str(SHOTS / "filhotes-uma-recusada.png"))

	page.check("#ciencia-pagamento-check")
	page.check("#ciencia-acompanhamento-check")
	confirmar_e_salvar(page, "filhotes")


def conferir_ficha(page, novo_associado, passo, badge_do_jovem, badges_dos_responsaveis):
	print(f"\n== Ficha da recepção ({passo}) ==")
	page.goto(f"{BASE}/recepcao/ficha_registro?name={novo_associado}")
	page.wait_for_selector(".ficha-header__meta")
	page.screenshot(path=str(SHOTS / f"ficha-{passo}.png"), full_page=True)

	bloco = page.locator(".ficha-header__meta > div").last.inner_text().strip().split("\n")
	checa("rótulo do bloco", bloco[0].strip(), "Carteirinha física")
	checa("badge do jovem", bloco[-1].strip(), badge_do_jovem)

	badges = page.locator(".responsavel-card__header .badge").all_inner_texts()
	checa("badges dos responsáveis", [b.strip() for b in badges], badges_dos_responsaveis)


def rodar_no_navegador(docs):
	from playwright.sync_api import sync_playwright

	with sync_playwright() as p:
		browser = p.chromium.launch(
			executable_path=CHROME,
			args=["--no-sandbox", f"--host-resolver-rules=MAP {SITE} 127.0.0.1"],
		)
		contexto = browser.new_context(viewport={"width": 1400, "height": 1000})
		contexto.add_cookies([{"name": "sid", "value": pegar_sid(), "domain": SITE, "path": "/"}])
		page = contexto.new_page()
		page.on("pageerror", lambda erro: falhas.append(f"erro de JS na página: {erro}"))

		cenario_lobinho(page, docs)
		conferir_ficha(page, docs["lobinho"], "lobinho", "Não", ["1º Responsável"])

		cenario_filhotes(page, docs)
		conferir_ficha(
			page,
			docs["filhote"],
			"filhotes",
			"Sim",
			["1º Responsável", "Será registrado", "Carteirinha física", "Será registrado"],
		)

		browser.close()


def main():
	import frappe

	SHOTS.mkdir(parents=True, exist_ok=True)

	frappe.init(site=SITE, sites_path="/workspace/frappe-bench/sites")
	frappe.connect()
	try:
		docs = semear()
		rodar_no_navegador(docs)
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
