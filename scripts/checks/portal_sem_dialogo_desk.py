#!/usr/bin/env python3
"""Barra APIs de diálogo do Desk sem equivalente no portal.

As páginas do portal (gris/www, gris/templates) usam o design system Basecoat e não
carregam o CSS do Desk. Qualquer modal Bootstrap do Frappe — frappe.msgprint,
frappe.confirm, frappe.ui.Dialog, frappe.prompt... — aparece sem estilo: o botão de
fechar vira um X gigante e a mensagem fica largada no rodapé da página.

`design-system-init.js` redireciona algumas dessas APIs para o design system (os
"shims"). Este script garante duas coisas:

1. cada shim declarado em `PORTAL_SHIMS` continua instalado em design-system-init.js;
2. nenhum arquivo do portal usa uma API de diálogo do Desk que não tenha shim.

Roda no pre-commit (e portanto no CI) e em `gris/tests/test_portal_sem_dialogo_desk.py`.
Uso: python scripts/checks/portal_sem_dialogo_desk.py  (sai com 1 se houver violação)
"""

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
APP = RAIZ / "gris"
DESIGN_SYSTEM_INIT = APP / "public" / "design_system" / "js" / "design-system-init.js"

#: APIs do Desk redirecionadas para o design system em design-system-init.js.
#: `frappe.throw` não precisa de shim próprio: no cliente ele chama `frappe.msgprint`.
PORTAL_SHIMS = ("show_alert", "msgprint", "confirm")

#: APIs do Desk que abrem diálogo/modal Bootstrap e não têm shim no portal.
API_PROIBIDA = re.compile(
	r"\bfrappe\.(?:"
	r"ui\.[A-Za-z_]\w*"  # frappe.ui.Dialog, frappe.ui.FileUploader, frappe.ui.form.*...
	r"|prompt|warn"
	r"|msg_dialog|update_msgprint|hide_msgprint|error_dialog"
	r")\b"
)

#: Usos conhecidos e aceitos, por (arquivo relativo à raiz, API). Cada entrada precisa
#: de justificativa; o ideal é zerar esta lista.
EXCECOES = {
	# Legado: frappe.ui.FileUploader não está no bundle web, então nas páginas do portal o
	# código só testa a existência e cai no aviso "Uploader indisponível." (via msgprint).
	("gris/www/calendario/importar.js", "frappe.ui.FileUploader"),
	("gris/www/financeiro/contas.js", "frappe.ui.FileUploader"),
}

_COMENTARIOS = re.compile(
	r"/\*.*?\*/"  # /* bloco */
	r"|\{#.*?#\}"  # {# Jinja #}
	r"|<!--.*?-->"  # <!-- HTML -->
	r"|(?<![:\"'\\])//[^\n]*",  # // linha (sem pegar "https://")
	re.DOTALL,
)


def _sem_comentarios(texto: str) -> str:
	"""Troca comentários por espaços, preservando as quebras de linha (e a numeração)."""
	return _COMENTARIOS.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), texto)


def arquivos_do_portal() -> list[Path]:
	"""JS e HTML servidos pelas páginas do portal.

	Inclui os scripts de gris/public/js referenciados por alguma página do portal (ou pelo
	`web_include_js`); os demais são do Desk, onde o modal Bootstrap tem estilo.
	"""
	paginas = [
		*sorted((APP / "www").rglob("*.js")),
		*sorted((APP / "www").rglob("*.html")),
		*sorted((APP / "templates").rglob("*.html")),
	]
	componentes = sorted((APP / "public" / "design_system" / "js" / "components").glob("*.js"))

	referencias = "\n".join(p.read_text(encoding="utf-8") for p in [*paginas, APP / "hooks.py"])
	compartilhados = sorted(
		p for p in (APP / "public" / "js").glob("*.js") if f"/assets/gris/js/{p.name}" in referencias
	)
	return [*paginas, *componentes, *compartilhados]


def shims_ausentes() -> list[str]:
	"""Shims de `PORTAL_SHIMS` que não estão mais atribuídos em design-system-init.js."""
	codigo = _sem_comentarios(DESIGN_SYSTEM_INIT.read_text(encoding="utf-8"))
	return [nome for nome in PORTAL_SHIMS if not re.search(rf"window\.frappe\.{re.escape(nome)}\s*=", codigo)]


def apis_proibidas_no_codigo(codigo: str) -> list[tuple[int, str]]:
	"""(linha, API) de cada API de diálogo do Desk sem shim, ignorando comentários."""
	return [
		(numero, match.group(0))
		for numero, linha in enumerate(_sem_comentarios(codigo).splitlines(), start=1)
		for match in API_PROIBIDA.finditer(linha)
	]


def usos_proibidos() -> list[tuple[str, int, str]]:
	"""(arquivo, linha, API) de cada uso fora de `EXCECOES` nos arquivos do portal."""
	encontrados = []
	for arquivo in arquivos_do_portal():
		relativo = arquivo.relative_to(RAIZ).as_posix()
		for numero, api in apis_proibidas_no_codigo(arquivo.read_text(encoding="utf-8")):
			if (relativo, api) not in EXCECOES:
				encontrados.append((relativo, numero, api))
	return encontrados


def main() -> int:
	erros = []
	for nome in shims_ausentes():
		erros.append(
			f"{DESIGN_SYSTEM_INIT.relative_to(RAIZ)}: shim de frappe.{nome} não está instalado "
			f"(esperado `window.frappe.{nome} = ...`)."
		)
	for arquivo, linha, api in usos_proibidos():
		erros.append(
			f"{arquivo}:{linha}: {api} abre um modal do Desk, que no portal aparece sem estilo. "
			"Use o design system (toast via frappe.show_alert/msgprint, <dialog> do Basecoat, "
			"frappe.confirm) ou crie o shim em design-system-init.js e registre em PORTAL_SHIMS."
		)

	for erro in erros:
		print(erro, file=sys.stderr)
	return 1 if erros else 0


if __name__ == "__main__":
	sys.exit(main())
