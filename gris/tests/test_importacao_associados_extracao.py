"""Extração e validação do relatório de associados do SIGUE, e o carimbo da última importação.

O relatório mudou de layout: o nome do associado deixou de ter rótulo (vem sozinho na linha
depois de "Dados pessoais") e o único `Nome:` do registro passou a ser o do responsável. O
parser antigo separava os registros por `Dados pessoais\\nNome:`, então juntava tudo num só e
gravava o nome da mãe no associado. A seção (`Seção:`, com acento) nunca era lida porque o
padrão procurava `Secao:`.

Todos os dados aqui são fictícios.
"""

import os
import tempfile
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.associate import importer
from gris.api.associate.importer import (
	_parse_scout_data,
	_validar_documento,
	_validar_registro,
	parse_associates_report,
	ultima_importacao_associados,
)

CABECALHO = """Retirado por Pessoa Exemplo de registro 999999
Escoteiros do Brasil
AXTU - Sistema de Informações e Gerenciamento de Unidades Escoteiras
Relatório Customizável
"""

# Beneficiário com responsável; o bloco do responsável atravessa a quebra de página.
JOVEM = """Dados pessoais
JOAO EXEMPLO DA SILVA
Registro: 1000001-1
Endereço completo: Rua Exemplo, 1
Unidade escoteira local: 147/SP
Categoria - 1º Função: Beneficiário
Categoria - 2º Função: Não se aplica
Categoria - 3º Função: Não se aplica
Função - 1º Função: Jovem
Função - 2º Função: Não se aplica
Função - 3º Função: Não se aplica
Ramo - 1º Função: Escoteiro
Ramo - 2º Função: Não se aplica
Ramo - 3º Função: Não se aplica
Nível - 1º Função: Local
Nível - 2º Função: Não se aplica
Nível - 3º Função: Não se aplica
Seção: Tropa Exemplo
Equipe: Patrulha Lobo
Celular: (11) 91111-1111
E-mail: joao@example.com
RG: 1234567/SSP/SP
CPF: 11144477735
Data Nascimento: 01/02/2012
Cidade: BARUERI
Número da UEL: 147
Sexo: M
Raça ou Cor: Parda
Validade Registro: 31/05/2027
id@escoteiro: joao.exemplo@escoteiros.org.br
Dados responsável
Nome: MARIA EXEMPLO DA SILVA
Endereço: Rua Exemplo, 1
Profissão: Comerciante
Local de Trabalho: Loja Exemplo
Escolaridade: Não informado
Celular: (11) 92222-2222
E-mail: maria@example.com
RG - Órgão Expedidor: /
CPF: 52998224725
"""

# Escotista sem seção e sem bloco de responsável.
ESCOTISTA = """Dados pessoais
ANA EXEMPLO ESCOTISTA
Registro: 1000002-2
Endereço completo: Rua Exemplo, 2
Unidade escoteira local: 147/SP
Categoria - 1º Função: Escotista
Função - 1º Função: Assistente
Ramo - 1º Função: Pioneiro
Nível - 1º Função: Local
Fone Residencial: (11) 3333-3333
Celular: (11) 93333-3333
E-mail: ana@example.com
RG: 7654321/SSP/SP
CPF: 39053344705
Data Nascimento: 10/10/1990
Cidade: BARUERI
Número da UEL: 147
Sexo: F
Raça ou Cor: Branca
Validade Registro: 31/05/2027
APF: PESSOA APF EXEMPLO
"""

# Layout anterior: nome com rótulo e "Numero da UEL" sem acento.
LAYOUT_ANTIGO = """Dados pessoais
Nome: PEDRO EXEMPLO ANTIGO
Registro: 1000003-3
Categoria - 1º Função: Beneficiário
Função - 1º Função: Jovem
Ramo - 1º Função: Lobinho
Secao: Alcateia Exemplo
Celular: (11) 94444-4444
E-mail: pedro@example.com
CPF: 11144477735
Numero da UEL: 147
Dados responsável
Nome: PAULA EXEMPLO ANTIGO
Celular: (11) 95555-5555
CPF: 52998224725
"""


def _relatorio(*registros: str) -> str:
	return CABECALHO + "".join(registros)


class TestExtracaoLayoutNovo(FrappeTestCase):
	def test_separa_um_registro_por_dados_pessoais(self):
		scouts = _parse_scout_data(_relatorio(JOVEM, ESCOTISTA))

		self.assertEqual([s["Registro"] for s in scouts], ["1000001-1", "1000002-2"])

	def test_nome_sem_rotulo_e_do_associado_e_nao_do_responsavel(self):
		jovem = _parse_scout_data(_relatorio(JOVEM))[0]

		self.assertEqual(jovem["Nome"], "JOAO EXEMPLO DA SILVA")
		self.assertEqual(jovem["Nome_responsavel"], "MARIA EXEMPLO DA SILVA")

	def test_campos_pessoais_e_do_responsavel_ficam_em_seus_blocos(self):
		jovem = _parse_scout_data(_relatorio(JOVEM))[0]

		self.assertEqual(jovem["CPF"], "11144477735")
		self.assertEqual(jovem["Celular"], "(11) 91111-1111")
		self.assertEqual(jovem["Email"], "joao@example.com")
		self.assertEqual(jovem["CPF_responsavel"], "52998224725")
		self.assertEqual(jovem["Celular_responsavel"], "(11) 92222-2222")
		self.assertEqual(jovem["Email_responsavel"], "maria@example.com")
		self.assertEqual(jovem["Profissao_responsavel"], "Comerciante")
		self.assertEqual(jovem["Escolaridade_responsavel"], "")

	def test_secao_uel_e_id_escoteiros(self):
		jovem = _parse_scout_data(_relatorio(JOVEM))[0]

		self.assertEqual(jovem["Secao"], "Tropa Exemplo")
		self.assertEqual(jovem["Equipe"], "Patrulha Lobo")
		self.assertEqual(jovem["Numero_da_UEL"], "147")
		self.assertEqual(jovem["id_escoteiro"], "joao.exemplo@escoteiros.org.br")
		self.assertEqual(jovem["Categoria_1_Funcao"], "Beneficiário")
		self.assertEqual(jovem["Ramo_1_Funcao"], "Escoteiro")

	def test_registro_sem_secao_e_sem_responsavel(self):
		escotista = _parse_scout_data(_relatorio(JOVEM, ESCOTISTA))[1]

		self.assertEqual(escotista["Nome"], "ANA EXEMPLO ESCOTISTA")
		self.assertEqual(escotista["Secao"], "")
		self.assertEqual(escotista["Equipe"], "")
		self.assertEqual(escotista["Nome_responsavel"], "")
		self.assertEqual(escotista["CPF_responsavel"], "")
		self.assertEqual(escotista["CPF"], "39053344705")

	def test_cpf_do_responsavel_nao_entra_no_associado_sem_cpf(self):
		sem_cpf = JOVEM.replace("CPF: 11144477735\n", "")

		jovem = _parse_scout_data(_relatorio(sem_cpf))[0]

		self.assertEqual(jovem["CPF"], "")
		self.assertEqual(jovem["CPF_responsavel"], "52998224725")

	def test_layout_antigo_continua_extraindo(self):
		pedro = _parse_scout_data(_relatorio(LAYOUT_ANTIGO))[0]

		self.assertEqual(pedro["Nome"], "PEDRO EXEMPLO ANTIGO")
		self.assertEqual(pedro["Secao"], "Alcateia Exemplo")
		self.assertEqual(pedro["Numero_da_UEL"], "147")
		self.assertEqual(pedro["Nome_responsavel"], "PAULA EXEMPLO ANTIGO")


def _problemas_dos_registros(texto: str) -> list[str]:
	scouts = _parse_scout_data(texto)
	return [m for m in (_validar_registro(i, s) for i, s in enumerate(scouts, start=1)) if m]


class TestValidacaoDaExtracao(FrappeTestCase):
	def test_relatorio_completo_nao_tem_problemas(self):
		texto = _relatorio(JOVEM, ESCOTISTA)

		self.assertEqual(_validar_documento(texto, _parse_scout_data(texto)), [])
		self.assertEqual(_problemas_dos_registros(texto), [])

	def test_pdf_sem_texto(self):
		problemas = _validar_documento("  \n", [])

		self.assertEqual(len(problemas), 1)
		self.assertIn("texto selecionável", problemas[0])

	def test_layout_nao_reconhecido(self):
		texto = "Relatório de outra coisa\nTotal: 10\n"

		problemas = _validar_documento(texto, _parse_scout_data(texto))

		self.assertEqual(len(problemas), 1)
		self.assertIn("layout do relatório não foi reconhecido", problemas[0])

	def test_registro_sem_campos_obrigatorios(self):
		incompleto = ESCOTISTA.replace("CPF: 39053344705\n", "").replace(
			"Categoria - 1º Função: Escotista\n", ""
		)

		problemas = _problemas_dos_registros(_relatorio(JOVEM, incompleto))

		self.assertEqual(len(problemas), 1)
		self.assertIn("Registro 1000002-2", problemas[0])
		self.assertIn("categoria da 1ª função", problemas[0])
		self.assertIn("CPF", problemas[0])

	def test_cpf_com_tamanho_errado(self):
		problemas = _problemas_dos_registros(_relatorio(ESCOTISTA.replace("CPF: 39053344705", "CPF: 123")))

		self.assertEqual(len(problemas), 1)
		self.assertIn("CPF válido", problemas[0])

	def test_nome_igual_ao_do_responsavel_e_rejeitado(self):
		scout = _parse_scout_data(_relatorio(JOVEM))[0]
		scout["Nome"] = scout["Nome_responsavel"]

		self.assertIn("igual ao do responsável", _validar_registro(1, scout))


class TestImportacaoPorRegistro(FrappeTestCase):
	def setUp(self):
		arquivo = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
		arquivo.close()
		self.caminho = arquivo.name

	def tearDown(self):
		frappe.db.rollback()
		os.unlink(self.caminho)

	def _importar(self, texto):
		with (
			patch.object(importer, "_extract_text_from_pdf", return_value=texto),
			patch.object(importer, "_importar_linhas") as importar_linhas,
			patch.object(importer, "_sincronizar_secoes_do_organograma", return_value={}),
		):
			resultado = parse_associates_report(self.caminho)
		return resultado, importar_linhas

	def test_registro_com_problema_fica_de_fora_e_os_demais_sao_importados(self):
		incompleto = ESCOTISTA.replace("CPF: 39053344705\n", "")
		logs_antes = frappe.db.count("Log Importacao de Associados")

		resultado, importar_linhas = self._importar(_relatorio(incompleto, JOVEM))

		self.assertEqual(resultado["status"], "ok")
		self.assertEqual(resultado["total"], 2)
		self.assertEqual(resultado["errors"], 1)
		self.assertIn("Registro 1000002-2", resultado["error_details"][0])
		self.assertIn("não importado", resultado["error_details"][0])

		df = importar_linhas.call_args.args[0]
		self.assertEqual(list(df["Registro"]), ["1000001-1"])
		# O índice mantém a posição no relatório: o jovem é o 2º registro do PDF.
		self.assertEqual(list(df.index), [1])
		self.assertEqual(frappe.db.count("Log Importacao de Associados"), logs_antes + 1)

	def test_sem_nenhum_registro_aproveitavel_nada_e_gravado(self):
		incompleto = ESCOTISTA.replace("CPF: 39053344705\n", "")
		logs_antes = frappe.db.count("Log Importacao de Associados")

		resultado, importar_linhas = self._importar(_relatorio(incompleto))

		self.assertEqual(resultado["status"], "invalido")
		self.assertEqual(resultado["total"], 1)
		self.assertEqual(len(resultado["validation_errors"]), 1)
		importar_linhas.assert_not_called()
		self.assertEqual(frappe.db.count("Log Importacao de Associados"), logs_antes)

	def test_layout_nao_reconhecido_nao_grava_nada(self):
		logs_antes = frappe.db.count("Log Importacao de Associados")

		resultado, importar_linhas = self._importar("Relatório de outra coisa\n")

		self.assertEqual(resultado["status"], "invalido")
		importar_linhas.assert_not_called()
		self.assertEqual(frappe.db.count("Log Importacao de Associados"), logs_antes)


class TestUltimaImportacao(FrappeTestCase):
	USUARIO = "importador.carimbo@example.com"

	def setUp(self):
		if not frappe.db.exists("User", self.USUARIO):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": self.USUARIO,
					"first_name": "Ana",
					"last_name": "Importadora",
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.db.rollback()

	def _log(self, quando: str, owner: str) -> str:
		log = frappe.get_doc(
			{"doctype": "Log Importacao de Associados", "data_importacao": quando, "arquivo_origem": "x.pdf"}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Log Importacao de Associados", log.name, "owner", owner, update_modified=False)
		return log.name

	def test_usa_o_log_mais_recente_e_o_nome_de_quem_importou(self):
		self._log("2099-01-01 08:00:00", "Administrator")
		self._log("2099-03-05 14:07:00", self.USUARIO)

		self.assertEqual(
			ultima_importacao_associados(),
			{"quando": "05/03/2099 às 14:07", "por": "Ana Importadora"},
		)

	def test_sem_importacao(self):
		frappe.db.delete("Log Importacao de Associados")

		self.assertIsNone(ultima_importacao_associados())
