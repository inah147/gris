"""Seed do módulo Financeiro (contas fixas, pagamentos, transações, cobranças)."""

import random
from datetime import date, timedelta

import frappe

from ..credentials import get
from ..faker_helpers import fake, first_of_month
from ..safe_insert import all_names, first_name, safe_insert, set_single

# ===========================================================================
# Conta Fixa: cobre 4 cenários
# ===========================================================================


def seed_contas_fixas(n: int) -> list[str]:
	"""
	Cria contas fixas cobrindo:
	  - ativa contínua (despesa_temporaria=0, ativa=1)
	  - ativa temporária dentro do período
	  - inativa
	  - temporária com data já passada
	"""
	hoje = date.today()
	cenarios = [
		{
			"descricao": "Aluguel da Sede",
			"valor": 2500.0,
			"dia_vencimento": 5,
			"ativa": 1,
			"despesa_temporaria": 0,
		},
		{
			"descricao": "Energia Elétrica",
			"valor": 450.0,
			"dia_vencimento": 10,
			"ativa": 1,
			"despesa_temporaria": 0,
		},
		{
			"descricao": "Aluguel Acampamento Verão",
			"valor": 800.0,
			"dia_vencimento": 15,
			"ativa": 1,
			"despesa_temporaria": 1,
			"data_inicio": hoje - timedelta(days=30),
			"data_termino": hoje + timedelta(days=60),
		},
		{
			"descricao": "Aluguel Material Acampamento Antigo",
			"valor": 300.0,
			"dia_vencimento": 20,
			"ativa": 0,
			"despesa_temporaria": 1,
			"data_inicio": hoje - timedelta(days=365),
			"data_termino": hoje - timedelta(days=180),
		},
	]
	created = 0
	names = []
	for cenario in cenarios[:n]:
		# Conta Fixa autoname = field:descricao, então descricao é o name
		if frappe.db.exists("Conta Fixa", cenario["descricao"]):
			names.append(cenario["descricao"])
			continue
		try:
			doc = frappe.get_doc({"doctype": "Conta Fixa", **cenario})
			doc.insert(ignore_permissions=True)
			names.append(doc.name)
			created += 1
		except Exception as e:
			print(f"  ⚠️  Conta Fixa {cenario['descricao']!r}: {e}")
	print(f"  → {created} Conta Fixa")
	return names


def seed_pagamentos_conta_fixa(conta_fixa_names: list[str]):
	"""Para cada conta fixa ativa contínua, gera 3 pagamentos cobrindo {Pago, Em Aberto, Atrasado}."""
	created = 0
	for nome_conta in conta_fixa_names:
		try:
			conta = frappe.get_doc("Conta Fixa", nome_conta)
		except frappe.DoesNotExistError:
			continue
		if not conta.ativa:
			continue
		statuses = ["Pago", "Em Aberto", "Atrasado"]
		for offset, status in zip([-2, 0, -1], statuses, strict=False):
			mes_ref = first_of_month(offset)
			# Idempotência por chave de negócio (controller sobrescreve titulo p/ mês em PT-BR)
			if frappe.db.exists("Pagamento Conta Fixa", {"conta": nome_conta, "mes_referencia": mes_ref}):
				continue
			try:
				# titulo será ajustado pelo controller em before_insert/validate
				frappe.get_doc(
					{
						"doctype": "Pagamento Conta Fixa",
						"conta": nome_conta,
						"status": status,
						"mes_referencia": mes_ref,
						"valor": conta.valor,
					}
				).insert(ignore_permissions=True)
				created += 1
			except Exception as e:
				print(f"  ⚠️  Pagamento Conta Fixa: {e}")
	print(f"  → {created} Pagamento Conta Fixa")


# ===========================================================================
# Pagamento Contribuição Mensal: histórico de N meses por beneficiário ativo
# ===========================================================================


def seed_pagamentos_contribuicao(meses: int):
	"""
	Para cada Associado beneficiário ativo, gera `meses` pagamentos com mix de status.

	Padrão: maioria Pago, alguns Atrasado, último Em Aberto.
	"""
	beneficiarios = frappe.get_all(
		"Associado",
		filters={"categoria": "Beneficiário", "status_no_grupo": "Ativo"},
		pluck="name",
	)
	if not beneficiarios:
		print("  → 0 Pagamento Contribuicao Mensal (sem beneficiários ativos)")
		return
	created = 0
	for assoc in beneficiarios:
		valor = frappe.db.get_value("Associado", assoc, "valor_contribuicao") or 60.0
		for i in range(meses):
			mes_ref = first_of_month(-i)
			# Idempotência: chave de negócio é (associado, mes_de_referencia)
			if frappe.db.exists(
				"Pagamento Contribuicao Mensal",
				{"associado": assoc, "mes_de_referencia": mes_ref},
			):
				continue
			# Distribuição de status: i==0 = Em Aberto, i==1 ou 4 = Atrasado, demais = Pago
			if i == 0:
				status = "Em Aberto"
			elif i in (1, 4):
				status = "Atrasado"
			else:
				status = "Pago"
			try:
				frappe.get_doc(
					{
						"doctype": "Pagamento Contribuicao Mensal",
						"associado": assoc,
						"status": status,
						"mes_de_referencia": mes_ref,
						"valor": valor,
						"atrasou": 1 if status in {"Atrasado", "Pago"} and i > 0 else 0,
					}
				).insert(ignore_permissions=True)
				created += 1
			except Exception as e:
				print(f"  ⚠️  Pagamento Contribuicao Mensal: {e}")
				break  # se um falha por validação cruzada, pula o resto pra esse assoc
	print(f"  → {created} Pagamento Contribuicao Mensal ({len(beneficiarios)} beneficiários x {meses} meses)")


# ===========================================================================
# Transações
# ===========================================================================


def seed_transacao_extrato_geral(n: int):
	carteiras = all_names("Carteira", limit=5)
	instituicoes = all_names("Instituicao Financeira", limit=5)
	categorias = all_names("Categoria de Transacao", limit=10)
	centros = all_names("Centro de Custo", limit=5)
	contas_fixas = all_names("Conta Fixa", limit=5)
	beneficiarios = frappe.get_all("Associado", limit=20, pluck="name")

	created = 0
	for i in range(n):
		txid = f"TXG-{2025}-{i:05d}"
		if frappe.db.exists("Transacao Extrato Geral", txid):
			continue
		valor = round(random.uniform(10, 5000), 2)
		debito_credito = random.choice(["Crédito", "Débito"])
		try:
			frappe.get_doc(
				{
					"doctype": "Transacao Extrato Geral",
					"id": txid,
					"descricao": fake.sentence(nb_words=4),
					"descricao_reduzida": fake.word(),
					"debito_credito": debito_credito,
					"origem": fake.company() if debito_credito == "Crédito" else "Conta UEL",
					"destino": fake.company() if debito_credito == "Débito" else "Conta UEL",
					"carteira": random.choice(carteiras) if carteiras else None,
					"valor": valor if debito_credito == "Crédito" else -valor,
					"valor_absoluto": valor,
					"data_transacao": date.today() - timedelta(days=random.randint(0, 180)),
					"timestamp_transacao": frappe.utils.now(),
					"metodo": random.choice(
						["Pix", "Cartão", "Boleto", "Tranferência entre carteiras", "Dinheiro", "Outro"]
					),
					"instituicao": random.choice(instituicoes) if instituicoes else None,
					"categoria": random.choice(categorias) if categorias else None,
					"fixo_variavel": random.choice(["Fixo", "Variável"]),
					"conta_fixa": random.choice(contas_fixas)
					if contas_fixas and random.random() < 0.3
					else None,
					"beneficiario": random.choice(beneficiarios)
					if beneficiarios and random.random() < 0.3
					else None,
					"centro_de_custo": random.choice(centros) if centros else None,
					"ordinaria_extraordinaria": random.choice(["Ordinária", "Extraordinária"]),
					"repasse_entre_contas": 0,
					"transacao_revisada": random.choice([0, 1]),
					"observacoes": fake.sentence(),
				}
			).insert(ignore_permissions=True)
			created += 1
		except Exception as e:
			print(f"  ⚠️  Transacao Extrato Geral: {e}")
	print(f"  → {created} Transacao Extrato Geral")


def seed_transacao_btg(n: int):
	created = 0
	for i in range(n):
		txid = f"BTG-{2025}-{i:05d}"
		if frappe.db.exists("Transacao BTG Empresas", txid):
			continue
		try:
			frappe.get_doc(
				{
					"doctype": "Transacao BTG Empresas",
					"id": txid,
					"data_transacao": date.today() - timedelta(days=random.randint(0, 60)),
					"descricao": f"Transação BTG {i}",
					"valor": round(random.uniform(50, 5000), 2),
					"tipo": random.choice(["TED", "PIX", "Boleto"]),
				}
			).insert(ignore_permissions=True)
			created += 1
		except Exception as e:
			print(f"  ⚠️  Transacao BTG: {e}")
	print(f"  → {created} Transacao BTG Empresas")


def seed_transacao_infinitepay_extrato(n: int):
	created = 0
	for i in range(n):
		txid = f"IFP-EXT-{i:05d}"
		if frappe.db.exists("Transacao Infinitepay extrato", txid):
			continue
		try:
			frappe.get_doc(
				{
					"doctype": "Transacao Infinitepay extrato",
					"id": txid,
					"data_transacao": frappe.utils.now(),
					"tipo_transacao": random.choice(["Recebimento", "Repasse", "Taxa"]),
					"nome_transacao": fake.sentence(nb_words=3),
					"detalhe": fake.word(),
					"valor": round(random.uniform(10, 1000), 2),
					"tipo": random.choice(["Crédito", "Débito"]),
				}
			).insert(ignore_permissions=True)
			created += 1
		except Exception as e:
			print(f"  ⚠️  Transacao Infinitepay extrato: {e}")
	print(f"  → {created} Transacao Infinitepay extrato")


def seed_transacao_infinitepay_recebimento(n: int):
	"""Controller gera id por hash dos campos — checamos idempotência por numero_liquidacao."""
	created = 0
	for i in range(n):
		infinite_id = f"inf-{i:08d}"
		data_venda = f"2025-01-{(i % 28) + 1:02d} 12:00:00"
		total_parcelas = (i % 12) + 1
		numero_liquidacao = f"LIQ{i:08d}"
		# Idempotência por chave de negócio (numero_liquidacao é único nos dados gerados)
		if frappe.db.exists("Transacao Infinitepay recebimento", {"numero_liquidacao": numero_liquidacao}):
			continue
		try:
			frappe.get_doc(
				{
					"doctype": "Transacao Infinitepay recebimento",
					"infinite_id": infinite_id,
					"origem": fake.company(),
					"data_venda": data_venda,
					"autorizacao": fake.numerify("######"),
					"bandeira": random.choice(["Visa", "Master", "Elo"]),
					"tipo": "Crédito",
					"valor": round(random.uniform(50, 500), 2),
					"total_parcelas": total_parcelas,
					"numero_parcela": 1,
					"valor_parcela": round(random.uniform(10, 100), 2),
					"valor_parcela_liquido": round(random.uniform(10, 95), 2),
					"valor_parcela_recebido": round(random.uniform(10, 95), 2),
					"status": "Recebido",
					"data_deposito": date.today(),
					"numero_liquidacao": numero_liquidacao,
					"antecipada": "Não",
				}
			).insert(ignore_permissions=True)
			created += 1
		except Exception as e:
			print(f"  ⚠️  Transacao Infinitepay recebimento: {e}")
	print(f"  → {created} Transacao Infinitepay recebimento")


def seed_transacao_infinitepay_vendas(n: int):
	created = 0
	for i in range(n):
		txid = f"IFP-VEND-{i:05d}"
		if frappe.db.exists("Transacao Infinitepay vendas", txid):
			continue
		try:
			frappe.get_doc(
				{
					"doctype": "Transacao Infinitepay vendas",
					"infinite_id": txid,
					"data_hora": frappe.utils.now(),
					"meio_meio": "Cartão",
					"meio_bandeira": random.choice(["Visa", "Master", "Elo"]),
					"meio_parcelas": str(random.randint(1, 12)),
					"tipo_origem": "POS",
					"identificador": fake.numerify("##########"),
					"status": "Aprovado",
					"valor": round(random.uniform(50, 500), 2),
					"valor_liquido": round(random.uniform(45, 480), 2),
					"taxa_aplicada": round(random.uniform(1, 20), 2),
					"taxa_aplicada_perc": round(random.uniform(2, 5), 2),
					"plano": "Padrão",
					"origem_nome": fake.company(),
				}
			).insert(ignore_permissions=True)
			created += 1
		except Exception as e:
			print(f"  ⚠️  Transacao Infinitepay vendas: {e}")
	print(f"  → {created} Transacao Infinitepay vendas")


def seed_transacao_portao_3(n: int):
	"""Controller gera id por hash dos campos — idempotência por descricao única."""
	carteiras = all_names("Carteira", limit=5)
	created = 0
	for i in range(n):
		timestamp_str = f"2025-01-{(i % 28) + 1:02d} 12:00:00"
		descricao = f"Catraca Portão 3 - Acesso #{i}"
		valor = round(random.uniform(10, 200), 2)
		entrada_saida = "Entrada" if i % 2 == 0 else "Saída"
		carteira = carteiras[i % len(carteiras)] if carteiras else ""
		tipo = ["Pix", "Crédito"][i % 2]
		tipo_de_transacao = "Acesso"
		# Idempotência por descricao (única nos dados gerados)
		if frappe.db.exists("Transacao Portao 3", {"descricao": descricao}):
			continue
		try:
			frappe.get_doc(
				{
					"doctype": "Transacao Portao 3",
					"timestamp": timestamp_str,
					"valor": valor,
					"carteira": carteira or None,
					"tipo": tipo,
					"e2e": fake.numerify("##########"),
					"descricao": descricao,
					"entrada_saida": entrada_saida,
					"cartao_final": fake.numerify("####"),
					"tipo_de_transacao": tipo_de_transacao,
				}
			).insert(ignore_permissions=True)
			created += 1
		except Exception as e:
			print(f"  ⚠️  Transacao Portao 3: {e}")
	print(f"  → {created} Transacao Portao 3")


# ===========================================================================
# Cobrança Infinitepay
# ===========================================================================


def seed_cobranca_infinitepay(n: int):
	"""
	Cria Cobranças Infinitepay.

	OBS: o controller chama a API real do InfinitePay em `after_insert`.
	Por padrão pulamos no seed; defina `GRIS_SEED_RUN_INFINITEPAY=1` para
	rodar contra credenciais reais.
	"""
	import os

	if not os.getenv("GRIS_SEED_RUN_INFINITEPAY"):
		print("  → Cobranca Infinitepay pulado (API externa — set GRIS_SEED_RUN_INFINITEPAY=1 p/ rodar)")
		return
	created = 0
	for i in range(n):
		order_nsu = f"COB-{i:08d}"
		if frappe.db.exists("Cobranca Infinitepay", order_nsu):
			continue
		status = random.choice(["Pendente", "Pago", "Erro"])
		try:
			frappe.get_doc(
				{
					"doctype": "Cobranca Infinitepay",
					"order_nsu": order_nsu,
					"status": status,
					"link_pagamento": f"https://infinitepay.io/pay/{order_nsu}",
					"itens": [
						{
							"descricao": "Contribuição Mensal",
							"quantidade": 1,
							"preco": round(random.uniform(50, 200), 2),
						},
						{
							"descricao": "Taxa de Acampamento",
							"quantidade": 1,
							"preco": round(random.uniform(20, 100), 2),
						},
					],
					"redirect_url": "https://example.org/obrigado",
					"customer_name": fake.name(),
					"customer_email": fake.email(),
					"customer_phone": fake.numerify("119########"),
					"address_cep": fake.postcode(),
					"address_street": fake.street_name(),
					"address_neighborhood": fake.bairro(),
					"address_number": str(random.randint(1, 999)),
					"amount": random.randint(5000, 50000),
					"installments": random.randint(1, 6),
					"capture_method": "credit_card",
					"transaction_nsu": fake.numerify("##########") if status == "Pago" else "",
				}
			).insert(ignore_permissions=True)
			created += 1
		except Exception as e:
			print(f"  ⚠️  Cobranca Infinitepay: {e}")
	print(f"  → {created} Cobranca Infinitepay (+ Item Cobranca Infinitepay)")


# ===========================================================================
# Singles do módulo Financeiro
# ===========================================================================


def seed_singles_financeiro(_creds: dict):
	# Configuracao infinitepay
	set_single("Configuracao infinitepay", {"handle": "gris-uel-47"})
	print("  → Configuracao infinitepay atualizado")

	# Configuracoes Contribuicao Mensal
	set_single(
		"Configuracoes Contribuicao Mensal",
		{
			"valor_base": 60.0,
			"dia_vencimento": 10,
			"valor_atraso": 5.0,
		},
	)
	print("  → Configuracoes Contribuicao Mensal atualizado")


# ===========================================================================
# Orquestrador
# ===========================================================================


def seed_financeiro(creds: dict, n: dict):
	print("[financeiro]")
	# Singles primeiro: Cobranca Infinitepay valida Configuracao infinitepay.handle
	seed_singles_financeiro(creds)
	conta_fixa_names = seed_contas_fixas(n["conta_fixa"])
	seed_pagamentos_conta_fixa(conta_fixa_names)
	seed_pagamentos_contribuicao(n["meses_pagamento_contribuicao"])
	seed_transacao_extrato_geral(n["transacao_extrato_geral"])
	seed_transacao_btg(n["transacao_btg"])
	seed_transacao_infinitepay_extrato(n["transacao_infinitepay_extrato"])
	seed_transacao_infinitepay_recebimento(n["transacao_infinitepay_recebimento"])
	seed_transacao_infinitepay_vendas(n["transacao_infinitepay_vendas"])
	seed_transacao_portao_3(n["transacao_portao_3"])
	seed_cobranca_infinitepay(n["cobranca_infinitepay"])
