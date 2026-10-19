"""Seed do módulo de Compras: catálogo, pessoas e pedidos em todas as etapas do fluxo.

Monta um cenário que exercita a Lista de compras (`/compras/fila`) de ponta a ponta:
pedidos de várias seções aguardando compra, alguns já comprados, recebidos,
entregues e um cancelado, com datas espalhadas para que "há quantos dias" faça
sentido. As pessoas têm nome e seção, porque a lista precisa mostrar quem pediu.

Os usuários nascem com a senha `SENHA_SEED` — só para ambiente local. Para ver a
lista como quem compra nas três áreas, entre com `compras.gestora@seed.gris.local`.
"""

from datetime import timedelta

import frappe
from frappe.utils import getdate, today

from ..safe_insert import safe_insert

SOLICITACAO = "Solicitacao de Compra"
SENHA_SEED = "gris-seed-2026"
DOMINIO = "seed.gris.local"

PE = "Programa Educativo"
MANUTENCAO = "Manutenção"
ADMINISTRATIVO = "Administrativo"

# (nome, área, tipo, ramo, código, valor unitário)
CATALOGO = [
	("Distintivo de Progressão · Pata Tenra", PE, "Distintivo de Progressão", "Lobinho", "LOB-01", 8.5),
	("Distintivo de Progressão · Saltador", PE, "Distintivo de Progressão", "Lobinho", "LOB-02", 8.5),
	("Distintivo de Progressão · Rastreador", PE, "Distintivo de Progressão", "Lobinho", "LOB-03", 8.5),
	("Distintivo de Progressão · Pista", PE, "Distintivo de Progressão", "Escoteiro", "ESC-01", 9.0),
	("Distintivo de Progressão · Trilha", PE, "Distintivo de Progressão", "Escoteiro", "ESC-02", 9.0),
	("Distintivo de Progressão · Escalada", PE, "Distintivo de Progressão", "Sênior", "SEN-01", 9.5),
	("Distintivo de Progressão · Azimute", PE, "Distintivo de Progressão", "Sênior", "SEN-03", 9.5),
	("Especialidade · Primeiros Socorros", PE, "Especialidade", "Todos", "ESP-PS", 7.0),
	("Especialidade · Acampamento", PE, "Especialidade", "Todos", "ESP-AC", 7.0),
	("Especialidade · Culinária", PE, "Especialidade", "Todos", "ESP-CU", 7.0),
	("Insígnia Mundial do Meio Ambiente", PE, "Insígnia de Interesse Especial", "Todos", "IIE-MA", 12.0),
	("Numeral do Grupo", PE, "Distintivo de Identificação", "Todos", "ID-NUM", 5.0),
	("Distintivo de Monitor", PE, "Distintivo de Função", "Escoteiro", "FUN-MON", 6.0),
	("Lenço do Grupo", PE, "Outro", "Todos", "LENCO", 35.0),
	("Lâmpada LED 9W", MANUTENCAO, None, None, None, 12.9),
	("Fita isolante 20m", MANUTENCAO, None, None, None, 8.0),
	("Tinta acrílica branca 3,6L", MANUTENCAO, None, None, None, 89.9),
	("Cadeado 40mm", MANUTENCAO, None, None, None, 42.0),
	("Corda de sisal 10m", MANUTENCAO, None, None, None, 29.9),
	("Resma de papel A4", ADMINISTRATIVO, None, None, None, 32.0),
	("Caixa de canetas esferográficas (50 un.)", ADMINISTRATIVO, None, None, None, 48.0),
	("Toner para impressora", ADMINISTRATIVO, None, None, None, 189.0),
]

# (login, nome, sobrenome, papéis)
PESSOAS = [
	("mariana.souza", "Mariana", "Souza", []),  # Akelá da Alcateia
	("ricardo.lima", "Ricardo", "Lima", []),  # Chefe da Tropa Escoteira
	("fernanda.alves", "Fernanda", "Alves", []),  # Chefe da Tropa Sênior
	("paulo.castro", "Paulo Henrique", "Castro", []),  # Chefe do Clã Pioneiro
	("beatriz.nogueira", "Beatriz", "Nogueira", []),  # Chefe da Colônia de Castores
	("juliana.prado", "Juliana", "Prado", []),  # Voluntária da manutenção da sede
	("carlos.menezes", "Carlos", "Menezes", []),  # Secretaria do grupo
	(
		"compras.gestora",
		"Ana",
		"Rezende",
		["Gestor de Metodos", "Gestor de Manutencao", "Gestor Administrativo"],
	),
	("helena.ramos", "Helena", "Ramos", ["Gestor Financeiro"]),
]

COMPRADORA = "compras.gestora"

# Cada pedido: quem pede, área, ramo (só no PE), há quantos dias foi pedido, itens
# e até onde chegou no fluxo. As etapas guardam há quantos dias aconteceram.
PEDIDOS = [
	{
		"de": "mariana.souza",
		"area": PE,
		"ramo": "Lobinho",
		"dias": 12,
		"justificativa": "Progressões da Alcateia na cerimônia do próximo sábado.",
		"itens": [
			("Distintivo de Progressão · Pata Tenra", 6),
			("Distintivo de Progressão · Saltador", 4),
			("Especialidade · Primeiros Socorros", 3),
		],
	},
	{
		"de": "ricardo.lima",
		"area": PE,
		"ramo": "Escoteiro",
		"dias": 9,
		"justificativa": "Acampamento de patrulha: especialidades conquistadas e novos monitores.",
		"itens": [
			("Distintivo de Progressão · Pista", 5),
			("Especialidade · Acampamento", 8),
			("Distintivo de Monitor", 2),
		],
	},
	{
		"de": "fernanda.alves",
		"area": PE,
		"ramo": "Sênior",
		"dias": 5,
		"itens": [
			("Distintivo de Progressão · Escalada", 4),
			("Especialidade · Primeiros Socorros", 2),
			("Insígnia Mundial do Meio Ambiente", 6),
		],
	},
	{
		"de": "beatriz.nogueira",
		"area": PE,
		"ramo": "Filhotes",
		"dias": 2,
		"justificativa": "Promessa dos castores novos.",
		"itens": [("Lenço do Grupo", 10), ("Numeral do Grupo", 10)],
	},
	{
		"de": "paulo.castro",
		"area": PE,
		"ramo": "Pioneiro",
		"dias": 1,
		"itens": [("Especialidade · Culinária", 3), ("Lenço do Grupo", 4)],
	},
	{
		"de": "juliana.prado",
		"area": MANUTENCAO,
		"dias": 7,
		"justificativa": "Lâmpadas queimadas no salão principal e na sala da Tropa.",
		"itens": [("Lâmpada LED 9W", 12), ("Fita isolante 20m", 3)],
	},
	{
		"de": "carlos.menezes",
		"area": ADMINISTRATIVO,
		"dias": 3,
		"itens": [("Resma de papel A4", 5), ("Caixa de canetas esferográficas (50 un.)", 2)],
	},
	{
		"de": "ricardo.lima",
		"area": PE,
		"ramo": "Escoteiro",
		"dias": 20,
		"itens": [("Distintivo de Progressão · Trilha", 3)],
		"comprada": {"dias": 6, "fornecedor": "Loja Escoteira Central", "documento": "NF 10233"},
	},
	{
		"de": "juliana.prado",
		"area": MANUTENCAO,
		"dias": 15,
		"itens": [("Tinta acrílica branca 3,6L", 2), ("Cadeado 40mm", 3)],
		"comprada": {"dias": 4, "fornecedor": "Casa do Construtor"},
	},
	{
		"de": "mariana.souza",
		"area": PE,
		"ramo": "Lobinho",
		"dias": 25,
		"itens": [("Distintivo de Progressão · Rastreador", 5)],
		"comprada": {"dias": 14, "fornecedor": "Loja Escoteira Central"},
		"recebida": {"dias": 3},
	},
	{
		"de": "carlos.menezes",
		"area": ADMINISTRATIVO,
		"dias": 18,
		"itens": [("Toner para impressora", 1)],
		"comprada": {"dias": 10, "fornecedor": "Papelaria Central"},
		"recebida": {"dias": 2},
	},
	{
		"de": "fernanda.alves",
		"area": PE,
		"ramo": "Sênior",
		"dias": 40,
		"itens": [("Distintivo de Progressão · Azimute", 2)],
		"comprada": {"dias": 33, "fornecedor": "Loja Escoteira Central"},
		"recebida": {"dias": 28},
		"entregue": {"dias": 26},
	},
	{
		"de": "paulo.castro",
		"area": MANUTENCAO,
		"dias": 35,
		"itens": [("Corda de sisal 10m", 4)],
		"comprada": {"dias": 30, "fornecedor": "Casa do Construtor"},
		"recebida": {"dias": 27},
		"entregue": {"dias": 25},
	},
	{
		"de": "beatriz.nogueira",
		"area": PE,
		"ramo": "Filhotes",
		"dias": 16,
		"itens": [("Especialidade · Acampamento", 2)],
		"cancelada": {"dias": 14, "motivo": "Pedido em duplicidade com o da Tropa Escoteira."},
	},
]


def _email(login: str) -> str:
	return f"{login}@{DOMINIO}"


def _ha(dias: int):
	return getdate(today()) - timedelta(days=dias)


def seed_catalogo_compras() -> None:
	for nome, area, tipo, ramo, codigo, valor in CATALOGO:
		safe_insert(
			{
				"doctype": "Item de Catalogo de Compras",
				"nome": nome,
				"area": area,
				"tipo": tipo,
				"ramo": ramo,
				"codigo": codigo,
				"valor_unitario": valor,
				"ativo": 1,
			}
		)
	print(f"  → {len(CATALOGO)} Item de Catalogo de Compras")


def seed_pessoas_compras() -> None:
	criadas = 0
	for login, nome, sobrenome, papeis in PESSOAS:
		email = _email(login)
		if frappe.db.exists("User", email):
			continue
		usuario = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": nome,
				"last_name": sobrenome,
				"send_welcome_email": 0,
				"new_password": SENHA_SEED,
				"roles": [{"role": papel} for papel in papeis],
			}
		)
		usuario.insert(ignore_permissions=True)
		criadas += 1
	print(f"  → {criadas} User de compras (senha local: {SENHA_SEED})")


def _avancar(doc, status: str, campos: dict) -> None:
	doc.update(campos)
	doc.status = status
	doc.save(ignore_permissions=True)


def seed_solicitacoes_compras() -> None:
	if frappe.db.exists(SOLICITACAO, {"solicitante": ["like", f"%@{DOMINIO}"]}):
		print("  → Solicitacao de Compra do seed já existe, pulando")
		return

	precos = dict(
		frappe.get_all(
			"Item de Catalogo de Compras",
			filters={"name": ["in", [item[0] for item in CATALOGO]]},
			fields=["name", "valor_unitario"],
			as_list=True,
		)
	)
	compradora = _email(COMPRADORA)

	for pedido in PEDIDOS:
		doc = frappe.get_doc(
			{
				"doctype": SOLICITACAO,
				"solicitante": _email(pedido["de"]),
				"area": pedido["area"],
				"ramo": pedido.get("ramo"),
				"data_solicitacao": _ha(pedido["dias"]),
				"status": "Solicitada",
				"justificativa": pedido.get("justificativa"),
				"itens": [
					{"item_catalogo": nome, "quantidade": quantidade, "valor_unitario": precos.get(nome)}
					for nome, quantidade in pedido["itens"]
				],
			}
		)
		doc.insert(ignore_permissions=True)

		if cancelada := pedido.get("cancelada"):
			_avancar(
				doc,
				"Cancelada",
				{
					"motivo_cancelamento": cancelada["motivo"],
					"cancelada_por": doc.solicitante,
					"data_cancelamento": _ha(cancelada["dias"]),
				},
			)
			continue

		if comprada := pedido.get("comprada"):
			_avancar(
				doc,
				"Comprada",
				{
					"data_compra": _ha(comprada["dias"]),
					"valor_pago": doc.valor_estimado,
					"fornecedor": comprada.get("fornecedor"),
					"numero_documento": comprada.get("documento"),
					"comprado_por": compradora,
				},
			)
		if recebida := pedido.get("recebida"):
			_avancar(
				doc,
				"Recebida",
				{"data_recebimento": _ha(recebida["dias"]), "recebido_por": compradora},
			)
		if entregue := pedido.get("entregue"):
			_avancar(
				doc,
				"Entregue",
				{"data_entrega": _ha(entregue["dias"]), "entregue_por": doc.solicitante},
			)

	print(f"  → {len(PEDIDOS)} Solicitacao de Compra (todas as etapas do fluxo)")


def seed_compras(_creds: dict | None = None, _n: dict | None = None) -> None:
	print("[compras]")
	seed_catalogo_compras()
	seed_pessoas_compras()
	seed_solicitacoes_compras()
