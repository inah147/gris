"""Papéis concedidos nos drives compartilhados, com Administrador de conteúdo como padrão do voluntário."""

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.google_workspace import access_manager
from gris.patches import conceder_administrador_de_conteudo_aos_voluntarios as patch

DOCTYPE = "Drives Compartilhados Workspace"
EMAIL = "voluntario@escoteiros.org.br"
DRIVE_ID = "drive-teste"


class _Executavel:
	def __init__(self, resultado=None):
		self._resultado = resultado or {}

	def execute(self):
		return self._resultado


class _FakePermissoes:
	def __init__(self, existentes):
		self.existentes = existentes
		self.criadas = []
		self.atualizadas = []

	def list(self, **params):
		return _Executavel({"permissions": self.existentes})

	def create(self, **params):
		self.criadas.append(params)
		return _Executavel()

	def update(self, **params):
		self.atualizadas.append(params)
		return _Executavel()


class _FakeDrive:
	def __init__(self, existentes=None):
		self.permissoes = _FakePermissoes(existentes or [])

	def permissions(self):
		return self.permissoes


class TestConcessaoDoPapel(FrappeTestCase):
	def test_cria_com_a_grafia_que_a_api_exige(self):
		drive = _FakeDrive()

		resultado = access_manager.grant_drive_access_if_missing(drive, EMAIL, DRIVE_ID, "fileOrganizer")

		self.assertEqual(resultado, "created")
		self.assertEqual(drive.permissoes.criadas[0]["body"]["role"], "fileOrganizer")

	def test_colaborador_existente_vira_administrador_de_conteudo(self):
		drive = _FakeDrive([{"id": "p1", "emailAddress": EMAIL, "role": "writer"}])

		resultado = access_manager.grant_drive_access_if_missing(drive, EMAIL, DRIVE_ID, "fileOrganizer")

		self.assertEqual(resultado, "updated")
		self.assertEqual(drive.permissoes.atualizadas[0]["body"], {"role": "fileOrganizer"})

	def test_administrador_de_conteudo_existente_nao_e_tocado(self):
		drive = _FakeDrive([{"id": "p1", "emailAddress": EMAIL, "role": "fileOrganizer"}])

		resultado = access_manager.grant_drive_access_if_missing(drive, EMAIL, DRIVE_ID, "fileOrganizer")

		self.assertEqual(resultado, "unchanged")
		self.assertEqual(drive.permissoes.atualizadas, [])

	def test_administrador_e_concedido(self):
		drive = _FakeDrive([{"id": "p1", "emailAddress": EMAIL, "role": "fileOrganizer"}])

		resultado = access_manager.grant_drive_access_if_missing(drive, EMAIL, DRIVE_ID, "organizer")

		self.assertEqual(resultado, "updated")
		self.assertEqual(drive.permissoes.atualizadas[0]["body"], {"role": "organizer"})

	def test_papel_fora_da_lista_cai_para_leitor(self):
		drive = _FakeDrive()

		access_manager.grant_drive_access_if_missing(drive, EMAIL, DRIVE_ID, "owner")

		self.assertEqual(drive.permissoes.criadas[0]["body"]["role"], "reader")

	def test_opcoes_dos_campos_sao_os_papeis_concedidos(self):
		"""Opção que o código não conhece seria concedida como Leitor sem aviso."""
		campos = {
			DOCTYPE: ("permissao_padrao_beneficiario", "permissao_padrao_adulto_voluntario"),
			"Concessoes Manuais Workspace": ("tipo_acesso",),
		}
		for doctype, fieldnames in campos.items():
			meta = frappe.get_meta(doctype)
			for fieldname in fieldnames:
				with self.subTest(campo=fieldname):
					opcoes = meta.get_field(fieldname).options.split("\n")
					self.assertEqual(set(opcoes), set(access_manager.DRIVE_ROLES.values()))

	def test_voluntario_recebe_o_papel_configurado_no_drive(self):
		linha = frappe._dict(
			permissao_padrao_beneficiario="reader", permissao_padrao_adulto_voluntario="fileorganizer"
		)

		self.assertEqual(
			access_manager._resolve_drive_default_role(linha, frappe._dict(categoria="Escotista")),
			"fileOrganizer",
		)
		self.assertEqual(
			access_manager._resolve_drive_default_role(linha, frappe._dict(categoria="Beneficiário")),
			"reader",
		)


class TestPatchAdministradorDeConteudo(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def _inserir_drive(self, nome, papel_voluntario):
		linha = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"parent": "Configuracoes Google Workspace",
				"parenttype": "Configuracoes Google Workspace",
				"parentfield": "drives_compartilhados",
				"nome_drive": nome,
				"drive_id": f"id-{nome}",
				"permissao_padrao_beneficiario": "reader",
				"permissao_padrao_adulto_voluntario": papel_voluntario,
			}
		)
		linha.db_insert()
		return linha.name

	def test_drive_novo_ja_nasce_com_administrador_de_conteudo(self):
		self.assertEqual(frappe.new_doc(DOCTYPE).permissao_padrao_adulto_voluntario, "fileOrganizer")

	def test_colaborador_vira_administrador_de_conteudo_e_leitor_fica(self):
		colaborador = self._inserir_drive("teste-colaborador", "writer")
		leitor = self._inserir_drive("teste-leitor", "reader")

		patch.execute()

		self.assertEqual(
			frappe.db.get_value(DOCTYPE, colaborador, "permissao_padrao_adulto_voluntario"), "fileOrganizer"
		)
		self.assertEqual(frappe.db.get_value(DOCTYPE, leitor, "permissao_padrao_adulto_voluntario"), "reader")
