"""Testes da cobrança da contribuição mensal por link InfinitePay.

Cobrem as três pontas do fluxo que o gestor enxerga: quais competências entram
numa cobrança, o que a baixa automática escreve no extrato quando o pagamento é
confirmado, e o recorte que garante que o responsável só vê os beneficiários
vinculados a ele.
"""

import datetime
import hashlib
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate

from gris.api.financeiro.cobranca_contribuicao import (
	FINALIDADE_CONTRIBUICAO,
	ORIGEM_AUTOMATICA,
	PREFIXO_ID_TRANSACAO,
	_normalizar_competencias,
	conciliar_baixas_de_cobranca,
	emitir_cobranca,
	enviar_cobranca,
	lancar_baixa,
	montar_cobranca,
	montar_mensagem,
	on_cobranca_atualizada,
)
from gris.api.financeiro.contribuicoes import (
	CATEGORIA_CONTRIBUICAO,
	STATUS_ATRASADO,
	STATUS_PAGO,
	STATUS_PARCIAL,
	apurar_associados,
	calcular_vencimento,
	chave_mes,
	competencias_pendentes,
	construir_meses,
	montar_grade,
)
from gris.api.responsavel_acesso import get_beneficiarios_associados
from gris.financeiro.doctype.cobranca_infinitepay import cobranca_infinitepay as cobranca_doctype

HOJE = datetime.date(2026, 8, 22)
VALOR = 60.0
VALOR_ATRASO = 70.0


def _apagar(doctype: str, filtros: dict) -> None:
	for nome in frappe.get_all(doctype, filters=filtros, pluck="name"):
		frappe.delete_doc(doctype, nome, force=True, ignore_permissions=True)


def _nome_por_cpf(cpf: str) -> str:
	"""Associado e Responsavel são nomeados pelo md5 do CPF, que também é gravado hasheado.

	Procurar pelo CPF em claro não acha nada — o nome derivado é o único jeito de
	saber se o registro do teste já existe.
	"""
	return hashlib.md5(cpf.encode("utf-8")).hexdigest()


class TestCompetenciasDaCobranca(FrappeTestCase):
	"""Seleção das competências cobradas — lógica pura, sem banco."""

	def setUp(self):
		self.meses = construir_meses(6, HOJE)
		self.vencimentos = {chave_mes(mes): calcular_vencimento(mes, 10) for mes in self.meses}

	def _grade(self, recebido):
		contribuinte = {"valor_contribuicao": VALOR, "inicio_do_pagamento": "2026-01-01"}
		return montar_grade(contribuinte, self.meses, recebido, HOJE, self.vencimentos, VALOR)

	def test_normalizar_aceita_csv_e_lista_sem_repetir(self):
		self.assertEqual(_normalizar_competencias("2026-07,2026-06,2026-07"), ["2026-06", "2026-07"])
		self.assertEqual(_normalizar_competencias(["2026-06", " 2026-05 "]), ["2026-05", "2026-06"])
		self.assertEqual(_normalizar_competencias(None), [])
		self.assertEqual(_normalizar_competencias(""), [])

	def test_normalizar_recusa_competencia_invalida(self):
		for invalida in ("2026-13", "26-07", "julho", "2026/07"):
			with self.assertRaises(frappe.ValidationError):
				_normalizar_competencias(invalida)

	def test_pendentes_listam_os_meses_nao_quitados(self):
		grade = self._grade({})
		pendentes = competencias_pendentes(grade)
		self.assertEqual(
			[p["ym"] for p in pendentes],
			["2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"],
		)
		self.assertTrue(all(p["valor"] == VALOR for p in pendentes))

	def test_mes_parcial_entra_pelo_que_falta(self):
		grade = self._grade({"2026-07": {"valor": 20.0, "qtd": 1}})
		pendentes = {p["ym"]: p for p in competencias_pendentes(grade)}
		self.assertEqual(pendentes["2026-07"]["status"], STATUS_PARCIAL)
		self.assertEqual(pendentes["2026-07"]["valor"], 40.0)

	def test_mes_quitado_fica_fora_da_cobranca(self):
		grade = self._grade({"2026-07": {"valor": VALOR, "qtd": 1}})
		self.assertNotIn("2026-07", [p["ym"] for p in competencias_pendentes(grade)])

	def test_mensagem_traz_competencias_valor_e_link(self):
		texto = montar_mensagem(
			{
				"name": "CM-teste",
				"competencias": ["2026-06", "2026-07"],
				"valor_total": 120.0,
				"link_pagamento": "https://pag.exemplo/abc",
			},
			"Fulano de Tal",
		)
		self.assertIn("06/2026, 07/2026", texto)
		self.assertIn("https://pag.exemplo/abc", texto)
		self.assertIn("Fulano de Tal", texto)
		self.assertIn("às contribuições", texto)


class TestBaixaDaCobranca(FrappeTestCase):
	"""Do pagamento confirmado ao mês quitado na apuração."""

	CPF = "99000000001"

	def setUp(self):
		self.associado = self._criar_associado()
		_apagar("Cobranca Infinitepay", {"associado": self.associado})
		_apagar("Transacao Extrato Geral", {"beneficiario": self.associado})
		frappe.db.set_single_value("Configuracao infinitepay", "handle", "grupo-teste")
		# A apuração cobra o valor de atraso do mês vencido: o teste fixa os dois
		# valores para não depender do que estiver configurado no site.
		frappe.db.set_single_value(
			"Configuracoes Contribuicao Mensal",
			{"valor_base": VALOR, "valor_atraso": VALOR_ATRASO, "dia_vencimento": 10},
		)

	def _criar_associado(self) -> str:
		nome = _nome_por_cpf(self.CPF)
		if frappe.db.exists("Associado", nome):
			return nome
		doc = frappe.get_doc(
			{
				"doctype": "Associado",
				"cpf": self.CPF,
				"nome_completo": "Beneficiário de Teste",
				"data_de_nascimento": "2015-01-01",
				"categoria": "Beneficiário",
				"status_no_grupo": "Ativo",
				"status_cobranca": "Ativo",
				"valor_contribuicao": VALOR,
				"inicio_do_pagamento": "2026-01-01",
				"telefone_cobranca": "11999990000",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _sem_rede(self):
		"""Substitui a chamada à InfinitePay do `after_insert` por um link falso."""
		resposta = mock.Mock()
		resposta.json.return_value = {"checkout_url": "https://pag.exemplo/teste"}
		resposta.raise_for_status.return_value = None
		return mock.patch.object(cobranca_doctype.requests, "post", return_value=resposta)

	def _criar_cobranca(
		self,
		competencias: str,
		status: str = "Pendente",
		paid_amount: int = 0,
		preco: float = VALOR,
		sufixo: str = "",
		**campos,
	):
		"""Cobrança gravada sem sair para a rede, com um item por competência."""
		with self._sem_rede():
			doc = frappe.get_doc(
				{
					"doctype": "Cobranca Infinitepay",
					"order_nsu": f"CM-teste-{competencias.replace(',', '-')}-{status}{sufixo}",
					"status": status,
					"finalidade": FINALIDADE_CONTRIBUICAO,
					"associado": self.associado,
					"competencias": competencias,
					"paid_amount": paid_amount,
					"itens": [
						{
							"descricao": f"Contribuição {ym}",
							"quantidade": 1,
							"preco": preco,
							"competencia": f"{ym}-01",
						}
						for ym in competencias.split(",")
					],
					**campos,
				}
			)
			doc.insert(ignore_permissions=True)
		doc.reload()
		return doc

	def test_baixa_lanca_credito_de_contribuicao_no_extrato(self):
		cobranca = self._criar_cobranca("2026-06,2026-07", status="Pago", paid_amount=12000)
		nome_transacao = lancar_baixa(cobranca)

		transacao = frappe.get_doc("Transacao Extrato Geral", nome_transacao)
		self.assertEqual(transacao.debito_credito, "Crédito")
		self.assertEqual(transacao.categoria, CATEGORIA_CONTRIBUICAO)
		self.assertEqual(transacao.beneficiario, self.associado)
		self.assertEqual(float(transacao.valor), 120.0)
		# A competência mais antiga cobrada é a que ancora a apuração; o crédito
		# que sobra quita as seguintes.
		self.assertEqual(getdate(transacao.mes_competencia), datetime.date(2026, 6, 1))
		self.assertEqual(
			frappe.db.get_value("Cobranca Infinitepay", cobranca.name, "transacao_extrato"),
			nome_transacao,
		)

	def test_baixa_e_idempotente(self):
		cobranca = self._criar_cobranca("2026-06", status="Pago", paid_amount=6000)
		primeira = lancar_baixa(cobranca)
		cobranca.reload()
		segunda = lancar_baixa(cobranca)

		self.assertEqual(primeira, segunda)
		self.assertEqual(primeira, f"{PREFIXO_ID_TRANSACAO}{cobranca.name}")
		self.assertEqual(frappe.db.count("Transacao Extrato Geral", {"beneficiario": self.associado}), 1)

	def test_handler_ignora_cobranca_que_nao_foi_paga(self):
		cobranca = self._criar_cobranca("2026-06", status="Pendente")
		on_cobranca_atualizada(cobranca)
		self.assertEqual(frappe.db.count("Transacao Extrato Geral", {"beneficiario": self.associado}), 0)

	def test_handler_ignora_cobranca_avulsa(self):
		cobranca = self._criar_cobranca("2026-06", status="Pendente")
		cobranca.finalidade = "Avulsa"
		cobranca.status = "Pago"
		cobranca.paid_amount = 6000
		on_cobranca_atualizada(cobranca)
		self.assertEqual(frappe.db.count("Transacao Extrato Geral", {"beneficiario": self.associado}), 0)

	def test_confirmacao_de_pagamento_da_baixa_pelo_doc_event(self):
		"""O caminho real: o webhook salva a cobrança como Paga e o extrato recebe o crédito.

		Nenhuma chamada explícita a `lancar_baixa` aqui — quem dispara é o
		`on_update` registrado em `doc_events`.
		"""
		cobranca = self._criar_cobranca("2026-06", status="Pendente")
		self.assertEqual(frappe.db.count("Transacao Extrato Geral", {"beneficiario": self.associado}), 0)

		cobranca.status = "Pago"
		cobranca.paid_amount = 6000
		with self._sem_rede():
			cobranca.save(ignore_permissions=True)

		self.assertEqual(frappe.db.count("Transacao Extrato Geral", {"beneficiario": self.associado}), 1)
		self.assertTrue(frappe.db.get_value("Cobranca Infinitepay", cobranca.name, "transacao_extrato"))

	def test_pagamento_quita_o_mes_atrasado_na_apuracao(self):
		antes = apurar_associados([self.associado], 6, HOJE)[0]
		situacao_antes = {linha["ym"]: linha["status"] for linha in antes["linhas"]}
		self.assertEqual(situacao_antes["2026-06"], STATUS_ATRASADO)
		self.assertEqual(situacao_antes["2026-07"], STATUS_ATRASADO)

		# Dois meses vencidos custam o valor de atraso, não o valor em dia.
		total = round(2 * VALOR_ATRASO * 100)
		cobranca = self._criar_cobranca(
			"2026-06,2026-07", status="Pago", paid_amount=total, preco=VALOR_ATRASO
		)
		lancar_baixa(cobranca)

		depois = apurar_associados([self.associado], 6, HOJE)[0]
		situacao_depois = {linha["ym"]: linha["status"] for linha in depois["linhas"]}
		self.assertEqual(situacao_depois["2026-06"], STATUS_PAGO)
		self.assertEqual(situacao_depois["2026-07"], STATUS_PAGO)
		self.assertEqual(depois["total_recebido"], 2 * VALOR_ATRASO)

	def test_pagamento_do_valor_em_dia_quita_o_mes_atrasado(self):
		"""Pagar 60 num mês já vencido fecha o mês: o acréscimo é o que se cobra."""
		cobranca = self._criar_cobranca("2026-06", status="Pago", paid_amount=int(VALOR * 100))
		lancar_baixa(cobranca)

		depois = apurar_associados([self.associado], 6, HOJE)[0]
		junho = next(linha for linha in depois["linhas"] if linha["ym"] == "2026-06")
		self.assertEqual(junho["status"], STATUS_PAGO)
		self.assertEqual(junho["esperado"], VALOR_ATRASO)
		self.assertEqual(junho["falta"], 0.0)
		self.assertTrue(junho["quitado_sem_acrescimo"])

	def test_montar_cobranca_recusa_competencia_ja_quitada(self):
		cobranca = self._criar_cobranca("2026-06", status="Pago", paid_amount=int(VALOR * 100))
		lancar_baixa(cobranca)

		with self.assertRaises(frappe.ValidationError), self._sem_rede():
			montar_cobranca(self.associado, "2026-06", meses=6)

	def test_baixa_declara_os_meses_e_marca_os_pagamentos_como_pagos(self):
		"""A baixa detalha quanto quitou de cada mês, e a tela do gestor enxerga isso.

		A tela do gestor e o MCP leem o `Pagamento Contribuicao Mensal`; sem o
		detalhamento a baixa só aparecia na apuração pelas transações.
		"""
		_apagar("Pagamento Contribuicao Mensal", {"associado": self.associado})
		cobranca = self._criar_cobranca(
			"2026-06,2026-07", status="Pago", paid_amount=14500, preco=VALOR_ATRASO, capture_method="pix"
		)
		transacao = frappe.get_doc("Transacao Extrato Geral", lancar_baixa(cobranca))

		# O valor é o cobrado; o que passar disso (juros de parcelamento) fica fora.
		self.assertEqual(float(transacao.valor), 2 * VALOR_ATRASO)
		self.assertEqual(transacao.metodo, "Pix")
		self.assertEqual(
			[(getdate(d.mes_referencia), float(d.valor)) for d in transacao.competencias_contribuicao],
			[(datetime.date(2026, 6, 1), VALOR_ATRASO), (datetime.date(2026, 7, 1), VALOR_ATRASO)],
		)
		pagamentos = frappe.get_all(
			"Pagamento Contribuicao Mensal",
			filters={"associado": self.associado},
			fields=["mes_de_referencia", "status", "transacao_extrato"],
			order_by="mes_de_referencia asc",
		)
		self.assertEqual(
			[(getdate(p.mes_de_referencia), p.status, p.transacao_extrato) for p in pagamentos],
			[
				(datetime.date(2026, 6, 1), "Pago", transacao.name),
				(datetime.date(2026, 7, 1), "Pago", transacao.name),
			],
		)

	def test_link_antigo_pago_depois_do_mes_quitado_entra_como_credito(self):
		"""O mês já quitado por outro pagamento não é declarado de novo pela baixa."""
		primeira = self._criar_cobranca("2026-06", status="Pago", paid_amount=6000, sufixo="-a")
		lancar_baixa(primeira)

		# Gravada já como Paga, a cobrança dispara a baixa pelo `on_update`.
		with mock.patch.object(frappe, "log_error") as log_error:
			antiga = self._criar_cobranca("2026-06", status="Pago", paid_amount=6000, sufixo="-b")
			nome = lancar_baixa(antiga)

		transacao = frappe.get_doc("Transacao Extrato Geral", nome)
		self.assertEqual(transacao.competencias_contribuicao, [])
		self.assertEqual(getdate(transacao.mes_competencia), datetime.date(2026, 6, 1))
		log_error.assert_called_once()

	def test_emitir_cobranca_substitui_a_pendente_anterior(self):
		with self._sem_rede():
			primeira = emitir_cobranca(self.associado, "2026-06", meses=12)
		# As duas emissões caem no mesmo segundo; o order_nsu (que dá nome) precisa diferir.
		with (
			self._sem_rede(),
			mock.patch(
				"gris.api.financeiro.cobranca_contribuicao._proximo_order_nsu",
				return_value="CM-teste-segunda",
			),
		):
			segunda = emitir_cobranca(self.associado, "2026-06,2026-07", meses=12, origem=ORIGEM_AUTOMATICA)

		self.assertEqual(segunda["substituidas"], [primeira["name"]])
		self.assertEqual(
			frappe.db.get_value("Cobranca Infinitepay", primeira["name"], "status"), "Substituída"
		)
		emitida = frappe.get_doc("Cobranca Infinitepay", segunda["name"])
		self.assertEqual(emitida.origem, ORIGEM_AUTOMATICA)
		self.assertEqual(
			[(getdate(i.competencia), i.em_atraso) for i in emitida.itens],
			[(datetime.date(2026, 6, 1), 1), (datetime.date(2026, 7, 1), 1)],
		)

	def test_envio_registra_o_resultado_na_cobranca(self):
		cobranca = self._criar_cobranca("2026-06")

		with mock.patch("gris.utils.whatsapp.enviar_texto") as enviar:
			resultado = enviar_cobranca(cobranca.name, lembrete=True)
		enviar.assert_called_once()
		self.assertTrue(resultado["enviado"])
		registrado = frappe.db.get_value(
			"Cobranca Infinitepay",
			cobranca.name,
			["ultimo_envio_whatsapp", "lembretes_enviados", "resultado_ultimo_envio"],
			as_dict=True,
		)
		self.assertTrue(registrado.ultimo_envio_whatsapp)
		self.assertEqual(registrado.lembretes_enviados, 1)
		self.assertIn("Lembrete", registrado.resultado_ultimo_envio)

		frappe.db.set_value("Associado", self.associado, "telefone_cobranca", "")
		frappe.db.set_value("Cobranca Infinitepay", cobranca.name, "customer_phone", "")
		try:
			resultado = enviar_cobranca(cobranca.name)
		finally:
			frappe.db.set_value("Associado", self.associado, "telefone_cobranca", "11999990000")
		self.assertFalse(resultado["enviado"])
		self.assertIn(
			"Não enviado",
			frappe.db.get_value("Cobranca Infinitepay", cobranca.name, "resultado_ultimo_envio"),
		)

	# ── conciliação com o fechamento importado ──

	def _instituicao_infinitepay(self) -> None:
		if not frappe.db.exists("Instituicao Financeira", "Infinitepay"):
			frappe.get_doc({"doctype": "Instituicao Financeira", "nome": "Infinitepay"}).insert(
				ignore_permissions=True
			)

	def _venda_importada(self, id_venda: str, valor: float, data: datetime.date | None = None) -> str:
		"""A mesma venda como o fechamento da InfinitePay a grava: fonte Sistema, sem dono."""
		from gris.financeiro.doctype.transacao_extrato_geral.transacao_extrato_geral import (
			criar_transacao_de_sistema,
		)

		self._instituicao_infinitepay()
		_apagar("Transacao Extrato Geral", {"id": id_venda})
		return criar_transacao_de_sistema(
			{
				"id": id_venda,
				"descricao": "Pagamento em PIX de FULANO",
				"debito_credito": "Crédito",
				"valor": valor,
				"data_transacao": data or getdate(),
				"instituicao": "Infinitepay",
				"categoria": CATEGORIA_CONTRIBUICAO,
			}
		).name

	def _baixa_paga(self, competencias: str, sufixo: str, transaction_nsu: str = "") -> str:
		cobranca = self._criar_cobranca(
			competencias, status="Pago", paid_amount=6000, sufixo=sufixo, transaction_nsu=transaction_nsu
		)
		return lancar_baixa(cobranca)

	def _situacao(self, nome: str) -> tuple:
		return frappe.db.get_value(
			"Transacao Extrato Geral", nome, ["status_conciliacao", "excluir_do_total"]
		)

	def test_concilia_pelo_transaction_nsu_e_mantem_a_baixa(self):
		baixa = self._baixa_paga("2026-06", "-nsu", transaction_nsu="nsu-teste-0001")
		# Cartão: a importação traz o valor líquido da taxa.
		venda = self._venda_importada("nsu-teste-0001", 57.3, add_days(getdate(), -1))

		resultado = conciliar_baixas_de_cobranca()

		self.assertGreaterEqual(resultado["conciliadas"], 1)
		self.assertEqual(self._situacao(baixa), ("Conciliada", 0))
		self.assertEqual(self._situacao(venda), ("Conciliada", 1))
		self.assertEqual(frappe.db.get_value("Transacao Extrato Geral", venda, "transacao_conciliada"), baixa)

	def test_sem_nsu_concilia_quando_ha_uma_so_venda_candidata(self):
		baixa = self._baixa_paga("2026-06", "-pix")
		venda = self._venda_importada("pix-teste-0001", 60.0)

		conciliar_baixas_de_cobranca()

		self.assertEqual(self._situacao(baixa), ("Conciliada", 0))
		self.assertEqual(self._situacao(venda), ("Conciliada", 1))

	def test_sem_nsu_nao_concilia_na_duvida(self):
		"""Duas vendas de mesmo valor no mesmo dia para uma baixa só: fica para o gestor."""
		baixa = self._baixa_paga("2026-06", "-duvida")
		primeira = self._venda_importada("pix-teste-0002", 60.0)
		segunda = self._venda_importada("pix-teste-0003", 60.0)

		conciliar_baixas_de_cobranca()

		self.assertEqual(self._situacao(baixa), ("Não conciliada", 0))
		self.assertEqual(self._situacao(primeira), ("Não conciliada", 0))
		self.assertEqual(self._situacao(segunda), ("Não conciliada", 0))

	def test_montar_cobranca_cria_um_item_por_competencia(self):
		with self._sem_rede():
			resultado = montar_cobranca(self.associado, "2026-06,2026-07", meses=12)

		emitida = frappe.get_doc("Cobranca Infinitepay", resultado["name"])
		self.assertEqual(emitida.finalidade, FINALIDADE_CONTRIBUICAO)
		self.assertEqual(emitida.associado, self.associado)
		self.assertEqual(emitida.competencias, "2026-06,2026-07")
		self.assertEqual(len(emitida.itens), 2)
		# Os dois meses já venceram: a cobrança sai pelo valor de atraso.
		self.assertEqual(resultado["valor_total"], 2 * VALOR_ATRASO)


class TestRecorteDoResponsavel(FrappeTestCase):
	"""O responsável só apura os beneficiários vinculados a ele."""

	CPF_RESPONSAVEL = "99000000010"
	CPF_FILHO = "99000000011"
	CPF_ALHEIO = "99000000012"

	def setUp(self):
		self.responsavel = self._criar_responsavel()
		self.filho = self._criar_beneficiario(self.CPF_FILHO, "Filho Vinculado")
		self.alheio = self._criar_beneficiario(self.CPF_ALHEIO, "Beneficiário de Outra Família")
		self._criar_vinculo(self.responsavel, self.filho)

	def _criar_responsavel(self) -> str:
		nome = _nome_por_cpf(self.CPF_RESPONSAVEL)
		if frappe.db.exists("Responsavel", nome):
			return nome
		doc = frappe.get_doc(
			{
				"doctype": "Responsavel",
				"cpf": self.CPF_RESPONSAVEL,
				"nome_completo": "Responsável de Teste",
				"email": "responsavel.teste@exemplo.org",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _criar_beneficiario(self, cpf: str, nome: str) -> str:
		registro = _nome_por_cpf(cpf)
		if frappe.db.exists("Associado", registro):
			return registro
		doc = frappe.get_doc(
			{
				"doctype": "Associado",
				"cpf": cpf,
				"nome_completo": nome,
				"data_de_nascimento": "2015-01-01",
				"categoria": "Beneficiário",
				"status_no_grupo": "Ativo",
				"status_cobranca": "Ativo",
				"valor_contribuicao": VALOR,
				"inicio_do_pagamento": "2026-01-01",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _criar_vinculo(self, responsavel: str, associado: str) -> None:
		if frappe.db.exists(
			"Responsavel Vinculo", {"responsavel": responsavel, "beneficiario_associado": associado}
		):
			return
		frappe.get_doc(
			{
				"doctype": "Responsavel Vinculo",
				"responsavel": responsavel,
				"beneficiario_associado": associado,
			}
		).insert(ignore_permissions=True)

	def test_vinculo_lista_so_os_beneficiarios_do_responsavel(self):
		vinculados = get_beneficiarios_associados(self.responsavel)
		self.assertIn(self.filho, vinculados)
		self.assertNotIn(self.alheio, vinculados)

	def test_responsavel_sem_vinculo_nao_apura_ninguem(self):
		self.assertEqual(get_beneficiarios_associados(None), [])
		self.assertEqual(apurar_associados([], 6, HOJE), [])

	def test_apuracao_do_responsavel_cobre_apenas_o_vinculado(self):
		apurados = apurar_associados(get_beneficiarios_associados(self.responsavel), 6, HOJE)
		self.assertEqual([a["id"] for a in apurados], [self.filho])

	def test_dirigente_fica_fora_mesmo_vinculado(self):
		frappe.db.set_value("Associado", self.filho, "categoria", "Dirigente")
		try:
			apurados = apurar_associados([self.filho], 6, HOJE)
			self.assertEqual(apurados, [])
		finally:
			frappe.db.set_value("Associado", self.filho, "categoria", "Beneficiário")
