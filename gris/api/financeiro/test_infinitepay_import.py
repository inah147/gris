# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt
"""Testes dos leitores dos arquivos exportados pela Infinitepay.

Cobrem os formatos atuais (extrato HTML, vendas XML, recebimentos XML e
comprovante de transferência XML) e garantem que os formatos antigos
(OFX e CSV) continuam sendo lidos da mesma forma.
"""

import os
import tempfile

from frappe.tests.utils import FrappeTestCase

from gris.api.financeiro.infinitepay import (
	FORMATO_CSV,
	FORMATO_HTML,
	FORMATO_OFX,
	FORMATO_XML,
	TIPO_EXTRATO,
	TIPO_RECEBIMENTOS,
	TIPO_VENDAS,
	_detect_format,
	bank_reconcilliation,
	get_infinitepay_bank_statement_df,
	get_infinitepay_receipts_df,
	get_infinitepay_sales_df,
	identificar_tipo_arquivo,
)
from gris.www.financeiro.contas import reconciliar_e_inserir_infinitepay

# Extrato "Relatório de movimentações" da Conta Web: tabela externa de página,
# uma tabela por dia, data no cabeçalho e linha de "Saldo do dia" no fim.
EXTRATO_HTML = """<!DOCTYPE html><html lang="pt-BR"><body>
<table class="size-full">
  <thead><tr><td><header><h1>Relat&oacute;rio de movimenta&ccedil;&otilde;es</h1>
    <p>GRUPO ESCOTEIRO PROFESSORA INAH DE MELO N 147.<!-- --> - <!-- -->CNPJ<!-- -->: <!-- -->10.355.908/0001-71</p>
  </header></td></tr></thead>
  <tbody><tr><td><main>
    <table>
      <thead>
        <tr><td>Data</td><td>Hora</td><td>Tipo de transa&ccedil;&atilde;o</td><td>Nome</td><td>Detalhe</td><td>Valor (R$)</td></tr>
        <tr><td class="absolute" rowSpan="0">03 Mai, 2026</td></tr>
      </thead>
      <tbody>
        <tr><td></td><td>08:50</td><td>Pix</td><td>Pix Natallia de Moura Feitosa</td><td>Recebido</td><td>+60,00</td></tr>
        <tr><td></td><td>08:50</td><td>Pix</td><td>Pix Natallia de Moura Feitosa</td><td>Recebido</td><td>+60,00</td></tr>
        <tr><td></td><td>13:24</td><td>Pix</td><td>Pix Fornecedor Exemplo</td><td>Enviado</td><td>-1.234,56</td></tr>
        <tr><td colspan="4"></td><td>Saldo do dia</td><td>+&nbsp;1.863,67</td></tr>
      </tbody>
    </table>
    <table>
      <thead>
        <tr><td>Data</td><td>Hora</td><td>Tipo de transa&ccedil;&atilde;o</td><td>Nome</td><td>Detalhe</td><td>Valor (R$)</td></tr>
        <tr><td class="absolute" rowSpan="0">30 Mai, 2026</td></tr>
      </thead>
      <tbody>
        <tr><td></td><td>17:39</td><td>Dep&oacute;sito de vendas</td><td>Venda Nitro</td><td>Dep&oacute;sito InfinitePay</td><td>+12,50</td></tr>
        <tr><td colspan="4"></td><td>Saldo do dia</td><td>+&nbsp;641,61</td></tr>
      </tbody>
    </table>
  </main></td></tr></tbody>
</table>
</body></html>
"""

EXTRATO_OFX = """OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE

<OFX><BANKMSGSRSV1><STMTTRNRS><TRNUID>1<STATUS><CODE>0<SEVERITY>INFO</STATUS>
<STMTRS><CURDEF>BRL<BANKACCTFROM><BANKID>0001<ACCTID>16819007-2<ACCTTYPE>CHECKING</BANKACCTFROM>
<BANKTRANLIST><DTSTART>20260501<DTEND>20260531>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260503085000<TRNAMT>60.00<FITID>FIT-1<NAME>Pix Natallia de Moura Feitosa<MEMO>Recebido</STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260503132400<TRNAMT>-1234.56<FITID>FIT-2<NAME>Pix Fornecedor Exemplo<MEMO>Enviado</STMTTRN>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260530173900<TRNAMT>12.50<FITID>FIT-3<NAME>Vendas<MEMO>Deposito InfinitePay</STMTTRN>
</BANKTRANLIST><LEDGERBAL><BALAMT>1839.01<DTASOF>20260531</LEDGERBAL></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>
"""

# No XML de vendas cada <sale> tem um único filho cujo nome concatena os
# cabeçalhos e cujo texto é a linha CSV, com os valores em aspas duplicadas.
_TAG_VENDAS = (
	"data_e_hora_meio_meio_meio_bandeira_meio_parcelas_tipo_origem_tipo_dados_adicionais"
	"_identificador_status_valor_r_l_quido_r_taxa_aplicada_valor_r_taxa_aplicada_aplicada"
	"_plano_nsu_origem_nome"
)

# Cada item é uma linha de CSV só, quebrada em duas partes por causa do tamanho —
# daí a concatenação explícita com `+`, para não parecer vírgula esquecida.
_LINHAS_VENDAS = [
	"30/05/2026 17:39,Crédito,mastercard,À Vista,Maquininha,NS: PB1F252H77225,374112,Aprovada,"
	+ '""13,30"",""12,50"",""\'- 0,80"",6.01,Nitro,SPB1F252H7722521900320260530170009,""""',
	"30/05/2026 17:46,Dinheiro,money,À Vista,Maquininha,NS: PB1F252H77225,85811635,Aprovada,"
	+ '""5,00"",""5,00"",""0,00"",0,Outro,"""",""""',
	"30/05/2026 17:49,Pix,Pix,À Vista,Maquininha,NS: PB1F252H77225,E607469482026,Aprovada,"
	+ '""26,50"",""26,50"",""0,00"",0,Outro,2189843481,MARCELO ALVES BARBOSA',
	"29/05/2026 10:00,Crédito,visa,À Vista,Maquininha,NS: PB1F252H77225,999111,Negada,"
	+ '""99,00"",""99,00"",""0,00"",0,Nitro,SPB-NEGADA,""""',
]

VENDAS_XML = (
	'<?xml version="1.0" encoding="UTF-8"?>\n<sales_report>\n'
	+ "\n".join(
		f"  <sale>\n    <{_TAG_VENDAS}>{linha}</{_TAG_VENDAS}>\n  </sale>" for linha in _LINHAS_VENDAS
	)
	+ "\n</sales_report>\n"
)

RECEBIMENTOS_CSV = (
	"Infinite ID;Origem;Data da Venda;Autorização;Bandeira;Tipo;Valor (R$);Total de parcelas;"
	"Nº da Parcela;Valor da parcela (R$);Líquido (R$);Recebido (R$);Status;Data do Depósito;"
	"Número único de liquidação (NuLiquid);Antecipada\n"
	"SPB1F252H7722521900320260530170009;Maquininha;30/05/2026 17h39;374112;Mastercard;Crédito;"
	"13.3;1;1;13.3;12.5;12.5;Depositado;30/05/2026;734914465;Sim\n"
)

RECEBIMENTOS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<transaction_payments>
  <transaction>
    <infinite_id>SPB1F252H7722521900320260530170009</infinite_id>
    <origem>Maquininha</origem>
    <data_da_venda>30/05/2026 17h39</data_da_venda>
    <autoriza_o>374112</autoriza_o>
    <bandeira>Mastercard</bandeira>
    <tipo>Crédito</tipo>
    <valor_r>13.3</valor_r>
    <total_de_parcelas>1</total_de_parcelas>
    <n_da_parcela>1</n_da_parcela>
    <valor_da_parcela_r>13.3</valor_da_parcela_r>
    <l_quido_r>12.5</l_quido_r>
    <recebido_r>12.5</recebido_r>
    <status>Depositado</status>
    <data_do_dep_sito>30/05/2026</data_do_dep_sito>
    <n_mero_nico_de_liquida_o_nuliquid>734914465</n_mero_nico_de_liquida_o_nuliquid>
    <antecipada>Sim</antecipada>
  </transaction>
</transaction_payments>
"""

COMPROVANTE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<proof_of_transfer>
  <generated_at>2026-06-06T10:36:46-03:00</generated_at>
  <merchant><name>GRUPO ESCOTEIRO PROFESSORA INAH DE MELO N 147.</name></merchant>
  <period><start_date>2026-05-01</start_date><end_date>2026-05-31</end_date></period>
  <transfers>
    <transfer>
      <settlement_method>nitro_settlement</settlement_method>
      <transactions>
        <transaction>
          <nsu>SPB1F252H7722521900320260530170009</nsu>
          <capture_method>Maquininha</capture_method>
          <transaction_date>2026-05-30 17:39:13</transaction_date>
          <card_brand>mastercard</card_brand>
          <payment_method>credit</payment_method>
          <amount>13,30</amount>
          <installments>1</installments>
          <installment_number>1</installment_number>
          <net_amount>12,50</net_amount>
          <receivable_amount>12,50</receivable_amount>
          <status>Depositado</status>
          <payment_date>2026-05-30</payment_date>
          <cip_liquidation_id>734914465</cip_liquidation_id>
          <anticipated>true</anticipated>
        </transaction>
      </transactions>
    </transfer>
  </transfers>
</proof_of_transfer>
"""


def _arquivo(conteudo: str, sufixo: str) -> str:
	fd, caminho = tempfile.mkstemp(suffix=sufixo)
	with os.fdopen(fd, "w", encoding="utf-8") as f:
		f.write(conteudo)
	return caminho


class TestInfinitepayImport(FrappeTestCase):
	def setUp(self):
		self._temporarios = []

	def tearDown(self):
		for caminho in self._temporarios:
			try:
				os.remove(caminho)
			except OSError:
				pass

	def arquivo(self, conteudo: str, sufixo: str) -> str:
		caminho = _arquivo(conteudo, sufixo)
		self._temporarios.append(caminho)
		return caminho

	# ------------------------------------------------------------------
	# Detecção de formato

	def test_detecta_formato_pelo_conteudo_e_nao_pela_extensao(self):
		# A Infinitepay entrega o relatório HTML com extensão .ofx.
		self.assertEqual(_detect_format(self.arquivo(EXTRATO_HTML, ".ofx")), FORMATO_HTML)
		self.assertEqual(_detect_format(self.arquivo(EXTRATO_OFX, ".ofx")), FORMATO_OFX)
		self.assertEqual(_detect_format(self.arquivo(VENDAS_XML, ".txt")), FORMATO_XML)
		self.assertEqual(_detect_format(self.arquivo(RECEBIMENTOS_CSV, ".csv")), FORMATO_CSV)

	# ------------------------------------------------------------------
	# Extrato

	def test_extrato_html(self):
		df = get_infinitepay_bank_statement_df(self.arquivo(EXTRATO_HTML, ".ofx"))

		# A linha "Saldo do dia" não é lançamento.
		self.assertEqual(len(df), 4)

		primeira = df.iloc[0]
		self.assertEqual(str(primeira["date"]), "2026-05-03 08:50:00")
		self.assertEqual(primeira["value"], 60.0)
		self.assertEqual(primeira["type"], "credit")
		self.assertEqual(primeira["transaction_type"], "PIX")
		self.assertEqual(primeira["name"], "Pix Natallia de Moura Feitosa")
		self.assertEqual(primeira["memo"], "Recebido")

		debito = df[df["type"] == "debit"].iloc[0]
		self.assertEqual(debito["value"], -1234.56)
		self.assertEqual(str(debito["date"]), "2026-05-03 13:24:00")

		venda = df.iloc[3]
		self.assertEqual(str(venda["date"]), "2026-05-30 17:39:00")
		self.assertEqual(venda["transaction_type"], "Depósito de vendas")

	def test_extrato_html_gera_ids_estaveis_e_unicos(self):
		caminho = self.arquivo(EXTRATO_HTML, ".ofx")
		df1 = get_infinitepay_bank_statement_df(caminho)
		df2 = get_infinitepay_bank_statement_df(caminho)

		# Lançamentos idênticos no mesmo minuto não podem colidir...
		self.assertEqual(df1["fitid"].nunique(), len(df1))
		# ...e reimportar o mesmo arquivo tem que repetir os mesmos ids.
		self.assertEqual(list(df1["fitid"]), list(df2["fitid"]))

	def test_extrato_ofx_continua_funcionando(self):
		df = get_infinitepay_bank_statement_df(self.arquivo(EXTRATO_OFX, ".ofx"))

		self.assertEqual(len(df), 3)
		self.assertEqual(list(df["fitid"]), ["FIT-1", "FIT-2", "FIT-3"])
		self.assertEqual(list(df["transaction_type"]), ["PIX", "PIX", "Depósito de vendas"])
		self.assertEqual(float(df.iloc[1]["value"]), -1234.56)

	def test_extrato_em_formato_invalido_falha_com_mensagem(self):
		with self.assertRaises(ValueError):
			get_infinitepay_bank_statement_df(self.arquivo("a;b;c\n1;2;3\n", ".csv"))

	# ------------------------------------------------------------------
	# Vendas

	def test_vendas_xml(self):
		df = get_infinitepay_sales_df(self.arquivo(VENDAS_XML, ".xml"))

		# A venda negada é descartada.
		self.assertEqual(len(df), 3)

		cartao = df[df["meio_meio"] == "Crédito"].iloc[0]
		self.assertEqual(str(cartao["data_hora"]), "2026-05-30 17:39:00")
		self.assertEqual(cartao["valor"], 13.30)
		self.assertEqual(cartao["valor_liquido"], 12.50)
		self.assertAlmostEqual(cartao["taxa_aplicada"], 0.80, places=2)
		self.assertEqual(cartao["infinite_id"], "SPB1F252H7722521900320260530170009")

		pix = df[df["meio_meio"] == "Pix"].iloc[0]
		self.assertEqual(pix["valor"], 26.50)
		self.assertEqual(pix["origem_nome"], "MARCELO ALVES BARBOSA")

	def test_vendas_xml_em_dinheiro_recebe_id_sintetico(self):
		df = get_infinitepay_sales_df(self.arquivo(VENDAS_XML, ".xml"))
		dinheiro = df[df["meio_meio"] == "Dinheiro"].iloc[0]
		self.assertTrue(dinheiro["infinite_id"].startswith("infinitepay-dinheiro-"))

	def test_vendas_xml_com_colunas_faltando_falha(self):
		xml = (
			'<?xml version="1.0" encoding="UTF-8"?><sales_report><sale>'
			f"<{_TAG_VENDAS}>30/05/2026 17:39,Crédito,mastercard</{_TAG_VENDAS}>"
			"</sale></sales_report>"
		)
		with self.assertRaises(ValueError):
			get_infinitepay_sales_df(self.arquivo(xml, ".xml"))

	# ------------------------------------------------------------------
	# Recebimentos

	def test_recebimentos_xml_equivale_ao_csv(self):
		df_csv = get_infinitepay_receipts_df(self.arquivo(RECEBIMENTOS_CSV, ".csv"))
		df_xml = get_infinitepay_receipts_df(self.arquivo(RECEBIMENTOS_XML, ".xml"))

		self.assertEqual(len(df_csv), len(df_xml))
		for coluna in df_csv.columns:
			self.assertEqual(
				str(df_csv.iloc[0][coluna]),
				str(df_xml.iloc[0][coluna]),
				msg=f"coluna divergente: {coluna}",
			)

	def test_recebimentos_xml_campos(self):
		df = get_infinitepay_receipts_df(self.arquivo(RECEBIMENTOS_XML, ".xml"))
		linha = df.iloc[0]

		self.assertEqual(linha["infinite_id"], "SPB1F252H7722521900320260530170009")
		self.assertEqual(str(linha["data_venda"]), "2026-05-30 17:39:00")
		self.assertEqual(str(linha["data_deposito"]), "2026-05-30")
		self.assertEqual(linha["valor"], 13.3)
		self.assertEqual(linha["valor_parcela_liquido"], 12.5)
		self.assertEqual(int(linha["total_parcelas"]), 1)
		self.assertEqual(str(linha["numero_liquidacao"]), "734914465")
		self.assertEqual(linha["antecipada"], "Sim")

	def test_comprovante_de_transferencia_xml(self):
		df = get_infinitepay_receipts_df(self.arquivo(COMPROVANTE_XML, ".xml"))
		linha = df.iloc[0]

		self.assertEqual(len(df), 1)
		self.assertEqual(linha["infinite_id"], "SPB1F252H7722521900320260530170009")
		self.assertEqual(str(linha["data_venda"]), "2026-05-30 17:39:00")
		self.assertEqual(str(linha["data_deposito"]), "2026-05-30")
		self.assertEqual(linha["bandeira"], "Mastercard")
		self.assertEqual(linha["tipo"], "Crédito")
		self.assertEqual(linha["valor"], 13.30)
		self.assertEqual(linha["valor_parcela_liquido"], 12.50)
		self.assertEqual(str(linha["numero_liquidacao"]), "734914465")
		self.assertEqual(linha["antecipada"], "Sim")

	def test_xml_de_recebimentos_desconhecido_falha(self):
		with self.assertRaises(ValueError):
			get_infinitepay_receipts_df(self.arquivo("<algo_outro/>", ".xml"))

	# ------------------------------------------------------------------
	# Conciliação ponta a ponta

	def test_conciliacao_com_os_formatos_novos(self):
		df_extrato = get_infinitepay_bank_statement_df(self.arquivo(EXTRATO_HTML, ".ofx"))
		df_vendas = get_infinitepay_sales_df(self.arquivo(VENDAS_XML, ".xml"))
		df_recebimentos = get_infinitepay_receipts_df(self.arquivo(RECEBIMENTOS_XML, ".xml"))

		df = bank_reconcilliation(df_extrato, df_recebimentos, df_vendas)

		# Do extrato entram os 3 Pix (o depósito de vendas fica de fora, pois vem
		# do relatório de vendas); das vendas entram cartão e dinheiro.
		self.assertEqual(len(df), 5)
		self.assertEqual(sorted(df["tipo_origem"].unique()), ["Débito na conta", "Maquininha"])

		cartao = df[df["infinite_id"] == "SPB1F252H7722521900320260530170009"].iloc[0]
		self.assertEqual(cartao["valor_liquido"], 12.50)
		self.assertEqual(str(cartao["data_deposito"]), "2026-05-30")
		self.assertEqual(str(cartao["num_liquidacao"]), "734914465")

		enviado = df[df["valor_liquido"] < 0].iloc[0]
		self.assertEqual(
			enviado["origem_nome"], "GRUPO ESCOTEIRO PROFESSORA INAH DE MELO N 147. - INFINITEPAY"
		)

	# ------------------------------------------------------------------
	# Identificação do tipo de anexo (usada pela importação via e-mail, que não
	# pode confiar no nome do arquivo)

	def test_identifica_extrato_html_e_ofx(self):
		self.assertEqual(identificar_tipo_arquivo(self.arquivo(EXTRATO_HTML, ".ofx")), TIPO_EXTRATO)
		self.assertEqual(identificar_tipo_arquivo(self.arquivo(EXTRATO_OFX, ".ofx")), TIPO_EXTRATO)

	def test_identifica_vendas_xml_e_csv(self):
		self.assertEqual(identificar_tipo_arquivo(self.arquivo(VENDAS_XML, ".xml")), TIPO_VENDAS)
		csv_vendas_legado = ",".join(
			[
				"Data e Hora",
				"Meio (Meio)",
				"Meio (Bandeira)",
				"Meio (Parcelas)",
				"Tipo (Origem)",
				"Status",
				"Valor (R$)",
				"NSU",
			]
		)
		self.assertEqual(identificar_tipo_arquivo(self.arquivo(csv_vendas_legado, ".csv")), TIPO_VENDAS)

	def test_identifica_recebimentos_xml_e_csv(self):
		self.assertEqual(identificar_tipo_arquivo(self.arquivo(RECEBIMENTOS_XML, ".xml")), TIPO_RECEBIMENTOS)
		self.assertEqual(identificar_tipo_arquivo(self.arquivo(COMPROVANTE_XML, ".xml")), TIPO_RECEBIMENTOS)
		self.assertEqual(identificar_tipo_arquivo(self.arquivo(RECEBIMENTOS_CSV, ".csv")), TIPO_RECEBIMENTOS)

	def test_identifica_arquivo_desconhecido_como_none(self):
		self.assertIsNone(identificar_tipo_arquivo(self.arquivo("<algo_outro/>", ".xml")))
		self.assertIsNone(identificar_tipo_arquivo(self.arquivo("<nao e xml valido", ".xml")))
		# Texto solto sem cara de CSV de relatório (poucas colunas) não deve ser
		# classificado por eliminação — evita que um anexo qualquer no mesmo
		# e-mail (ex.: assinatura, logo) roube o lugar do relatório de verdade.
		self.assertIsNone(identificar_tipo_arquivo(self.arquivo("não é um relatório Infinitepay", ".txt")))


class TestReconciliarEInserirInfinitepay(FrappeTestCase):
	"""`reconciliar_e_inserir_infinitepay` é o núcleo reaproveitado pelo upload manual
	(`process_uploaded_files`) e pela importação automática via e-mail."""

	def setUp(self):
		self._temporarios = []

	def tearDown(self):
		for caminho in self._temporarios:
			try:
				os.remove(caminho)
			except OSError:
				pass

	def arquivo(self, conteudo: str, sufixo: str) -> str:
		caminho = _arquivo(conteudo, sufixo)
		self._temporarios.append(caminho)
		return caminho

	def test_insere_as_tres_tabelas_de_origem_e_e_idempotente(self):
		extrato = self.arquivo(EXTRATO_HTML, ".ofx")
		vendas = self.arquivo(VENDAS_XML, ".xml")
		recebimentos = self.arquivo(RECEBIMENTOS_XML, ".xml")

		primeiro = reconciliar_e_inserir_infinitepay(extrato, vendas, recebimentos)
		self.assertIsNotNone(primeiro["stats"])
		# 4 lançamentos no extrato, 3 vendas aprovadas (a "Negada" é descartada) e
		# 1 recebimento — ver `test_conciliacao_com_os_formatos_novos` acima.
		self.assertEqual(
			primeiro["stats"]["extrato"], {"total": 4, "inserted": 4, "skipped_exist": 0, "failed": 0}
		)
		self.assertEqual(
			primeiro["stats"]["vendas"], {"total": 3, "inserted": 3, "skipped_exist": 0, "failed": 0}
		)
		self.assertEqual(
			primeiro["stats"]["recebimentos"], {"total": 1, "inserted": 1, "skipped_exist": 0, "failed": 0}
		)
		self.assertEqual(primeiro["stats"]["geral"]["total"], 5)

		# Reimportar os mesmos 3 arquivos não duplica nada.
		segundo = reconciliar_e_inserir_infinitepay(extrato, vendas, recebimentos)
		self.assertEqual(segundo["stats"]["extrato"]["skipped_exist"], 4)
		self.assertEqual(segundo["stats"]["vendas"]["skipped_exist"], 3)
		self.assertEqual(segundo["stats"]["recebimentos"]["skipped_exist"], 1)
		self.assertEqual(segundo["stats"]["extrato"]["inserted"], 0)
		self.assertEqual(segundo["stats"]["vendas"]["inserted"], 0)
		self.assertEqual(segundo["stats"]["recebimentos"]["inserted"], 0)

	def test_formato_invalido_devolve_erro_sem_lancar_excecao(self):
		resultado = reconciliar_e_inserir_infinitepay(
			self.arquivo("não é um extrato", ".ofx"),
			self.arquivo(VENDAS_XML, ".xml"),
			self.arquivo(RECEBIMENTOS_XML, ".xml"),
		)
		self.assertIsNone(resultado["stats"])
		self.assertIn("Erro ao processar arquivos", resultado["summary_text"])
