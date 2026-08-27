"""Registro central das ferramentas expostas ao Claude (MCP).

Este módulo é a **fonte única de verdade** das ferramentas: cada ferramenta
declara nome, descrição, schema de argumentos (JSON Schema simplificado), papéis
autorizados e se é somente leitura. Os transportes (bridge stdio em
``mcp_server/`` e o endpoint HTTP em ``gris.api.mcp.http``) apenas traduzem esse
catálogo para o protocolo MCP — nenhuma regra de negócio ou de autorização vive
no cliente.

Contrato de retorno de ``executar``:
    sucesso -> {"ok": True, "data": <payload>}
    erro    -> ErroDeFerramenta (traduzido para {"ok": False, "error": {...}})
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

import frappe

# Papel que enxerga todas as ferramentas, seguindo o mesmo critério de
# gris.api.portal_access.user_has_access (System Manager tem acesso amplo).
PAPEL_ADMIN = "System Manager"

# Módulos que registram ferramentas. Importados sob demanda para evitar
# import circular (cada módulo importa este registro).
MODULOS_DE_FERRAMENTAS = (
	"gris.api.mcp.geral",
	"gris.api.mcp.associados",
	"gris.api.mcp.financeiro",
	"gris.api.mcp.contribuicoes",
	"gris.api.mcp.conciliacao",
	"gris.api.mcp.contas_fixas",
	"gris.api.mcp.orcamento",
)

LIMITE_PADRAO = 25
LIMITE_MAXIMO = 100

# Toda ferramenta de escrita ganha automaticamente o parâmetro de simulação
# (dry-run): o handler calcula o que mudaria e devolve o antes/depois sem gravar.
PARAMETRO_SIMULACAO = {
	"simular": {
		"type": "boolean",
		"default": False,
		"description": (
			"Se verdadeiro, apenas simula: mostra o que seria alterado, sem gravar nada. "
			"Use antes de operações em lote para conferir o resultado."
		),
	}
}


class ErroDeFerramenta(Exception):
	"""Erro previsto de ferramenta, com código estável para a integração."""

	def __init__(self, codigo: str, mensagem: str, detalhes: dict | None = None):
		super().__init__(mensagem)
		self.codigo = codigo
		self.mensagem = mensagem
		self.detalhes = detalhes or {}

	def as_dict(self) -> dict:
		erro: dict[str, Any] = {"code": self.codigo, "message": self.mensagem}
		if self.detalhes:
			erro["details"] = self.detalhes
		return {"ok": False, "error": erro}


@dataclass(frozen=True)
class Ferramenta:
	nome: str
	titulo: str
	descricao: str
	handler: Callable[..., Any]
	parametros: dict = field(default_factory=dict)
	obrigatorios: tuple[str, ...] = ()
	roles: tuple[str, ...] = ()
	somente_leitura: bool = True

	def parametros_efetivos(self) -> dict:
		"""Parâmetros declarados + os injetados pelo registro (simulação)."""
		if self.somente_leitura:
			return self.parametros
		return {**self.parametros, **PARAMETRO_SIMULACAO}

	def input_schema(self) -> dict:
		return {
			"type": "object",
			"properties": self.parametros_efetivos(),
			"required": list(self.obrigatorios),
			"additionalProperties": False,
		}

	def as_dict(self) -> dict:
		return {
			"nome": self.nome,
			"titulo": self.titulo,
			"descricao": self.descricao,
			"input_schema": self.input_schema(),
			"roles": list(self.roles),
			"somente_leitura": self.somente_leitura,
		}


_REGISTRO: dict[str, Ferramenta] = {}
_MODULOS_CARREGADOS = False


def ferramenta(
	nome: str,
	titulo: str,
	descricao: str,
	parametros: dict | None = None,
	obrigatorios: Iterable[str] = (),
	roles: Iterable[str] = (),
	somente_leitura: bool = True,
) -> Callable:
	"""Decorador que registra uma função como ferramenta MCP."""

	def decorador(fn: Callable) -> Callable:
		registrar(
			Ferramenta(
				nome=nome,
				titulo=titulo,
				descricao=descricao,
				handler=fn,
				parametros=parametros or {},
				obrigatorios=tuple(obrigatorios),
				roles=tuple(roles),
				somente_leitura=somente_leitura,
			)
		)
		return fn

	return decorador


def registrar(ferramenta_obj: Ferramenta) -> None:
	if ferramenta_obj.nome in _REGISTRO:
		raise ValueError(f"Ferramenta duplicada no registro: {ferramenta_obj.nome}")
	_REGISTRO[ferramenta_obj.nome] = ferramenta_obj


def carregar_ferramentas() -> dict[str, Ferramenta]:
	global _MODULOS_CARREGADOS
	if not _MODULOS_CARREGADOS:
		for modulo in MODULOS_DE_FERRAMENTAS:
			importlib.import_module(modulo)
		_MODULOS_CARREGADOS = True
	return _REGISTRO


# ---------------------------------------------------------------------------
# Autorização
# ---------------------------------------------------------------------------


def _papeis_do_usuario() -> set[str]:
	return set(frappe.get_roles(frappe.session.user))


def usuario_autorizado(ferramenta_obj: Ferramenta, papeis: set[str] | None = None) -> bool:
	papeis = papeis if papeis is not None else _papeis_do_usuario()
	if PAPEL_ADMIN in papeis:
		return True
	if not ferramenta_obj.roles:
		return True
	return any(papel in papeis for papel in ferramenta_obj.roles)


def _garantir_autenticado() -> None:
	if not getattr(frappe.session, "user", None) or frappe.session.user == "Guest":
		raise ErroDeFerramenta(
			"NAO_AUTENTICADO",
			"Sessão não autenticada. Configure a API key/secret de um usuário do GRIS.",
		)


# ---------------------------------------------------------------------------
# Validação de argumentos (JSON Schema simplificado)
# ---------------------------------------------------------------------------


def _erro_argumento(mensagem: str, detalhes: dict | None = None) -> ErroDeFerramenta:
	return ErroDeFerramenta("ARGUMENTO_INVALIDO", mensagem, detalhes)


def _converter(nome_campo: str, valor: Any, esquema: dict) -> Any:
	tipo = esquema.get("type", "string")

	if tipo == "integer":
		try:
			valor = int(valor)
		except (TypeError, ValueError):
			raise _erro_argumento(f"O parâmetro '{nome_campo}' precisa ser um número inteiro.")
		minimo, maximo = esquema.get("minimum"), esquema.get("maximum")
		if minimo is not None and valor < minimo:
			valor = minimo
		if maximo is not None and valor > maximo:
			valor = maximo
		return valor

	if tipo == "number":
		try:
			return float(valor)
		except (TypeError, ValueError):
			raise _erro_argumento(f"O parâmetro '{nome_campo}' precisa ser numérico.")

	if tipo == "boolean":
		if isinstance(valor, bool):
			return valor
		if isinstance(valor, str):
			return valor.strip().lower() in {"1", "true", "sim", "yes"}
		return bool(valor)

	if tipo == "array":
		if isinstance(valor, str):
			valor = [item.strip() for item in valor.split(",") if item.strip()]
		if not isinstance(valor, list):
			raise _erro_argumento(f"O parâmetro '{nome_campo}' precisa ser uma lista.")
		limite = esquema.get("maxItems")
		if limite is not None and len(valor) > limite:
			raise _erro_argumento(
				f"O parâmetro '{nome_campo}' aceita no máximo {limite} itens (recebidos {len(valor)})."
			)
		return valor

	if tipo == "object":
		if not isinstance(valor, dict):
			raise _erro_argumento(f"O parâmetro '{nome_campo}' precisa ser um objeto.")
		return valor

	valor = str(valor).strip()
	opcoes = esquema.get("enum")
	if opcoes and valor not in opcoes:
		raise _erro_argumento(
			f"Valor inválido para '{nome_campo}'. Opções aceitas: {', '.join(opcoes)}.",
			{"campo": nome_campo, "opcoes": list(opcoes)},
		)
	return valor


def validar_argumentos(ferramenta_obj: Ferramenta, argumentos: dict | None) -> dict:
	argumentos = dict(argumentos or {})
	esquemas = ferramenta_obj.parametros_efetivos()

	desconhecidos = sorted(set(argumentos) - set(esquemas))
	if desconhecidos:
		raise _erro_argumento(
			f"Parâmetros não reconhecidos: {', '.join(desconhecidos)}.",
			{"aceitos": sorted(esquemas)},
		)

	validados: dict[str, Any] = {}
	for nome_campo, esquema in esquemas.items():
		if nome_campo in argumentos and argumentos[nome_campo] not in (None, ""):
			validados[nome_campo] = _converter(nome_campo, argumentos[nome_campo], esquema)
		elif nome_campo in ferramenta_obj.obrigatorios:
			raise _erro_argumento(f"O parâmetro '{nome_campo}' é obrigatório.")
		elif "default" in esquema:
			validados[nome_campo] = esquema["default"]

	return validados


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------


def listar(incluir_indisponiveis: bool = False) -> list[dict]:
	"""Catálogo de ferramentas visíveis para o usuário da sessão."""
	_garantir_autenticado()
	papeis = _papeis_do_usuario()
	catalogo = []
	for ferramenta_obj in sorted(carregar_ferramentas().values(), key=lambda f: f.nome):
		autorizada = usuario_autorizado(ferramenta_obj, papeis)
		if not autorizada and not incluir_indisponiveis:
			continue
		dados = ferramenta_obj.as_dict()
		dados["autorizada"] = autorizada
		catalogo.append(dados)
	return catalogo


def executar(nome: str, argumentos: dict | None = None) -> dict:
	"""Executa uma ferramenta com autenticação, autorização e validação."""
	_garantir_autenticado()

	ferramentas = carregar_ferramentas()
	ferramenta_obj = ferramentas.get(nome)
	if not ferramenta_obj:
		raise ErroDeFerramenta(
			"FERRAMENTA_DESCONHECIDA",
			f"Ferramenta '{nome}' não existe.",
			{"disponiveis": sorted(ferramentas)},
		)

	if not usuario_autorizado(ferramenta_obj):
		raise ErroDeFerramenta(
			"PERMISSAO_NEGADA",
			f"Seu usuário não tem permissão para usar '{nome}'.",
			{"roles_necessarias": list(ferramenta_obj.roles)},
		)

	validados = validar_argumentos(ferramenta_obj, argumentos)
	dados = ferramenta_obj.handler(**validados)

	# Simulação não altera nada — só mutação real entra no log de auditoria.
	if not ferramenta_obj.somente_leitura and not validados.get("simular"):
		frappe.logger("gris_mcp").info(
			{
				"evento": "ferramenta_mutacao",
				"ferramenta": nome,
				"usuario": frappe.session.user,
				"argumentos": validados,
			}
		)

	return {"ok": True, "data": dados}


def normalizar_limite(limite: Any) -> int:
	try:
		limite = int(limite)
	except (TypeError, ValueError):
		return LIMITE_PADRAO
	return max(1, min(limite, LIMITE_MAXIMO))
