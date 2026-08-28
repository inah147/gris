"""
Entry-point do seed de dados de teste para o Gris.

Uso:
    bench --site <site> execute gris.scripts.seed.main.seed_test_data
    bench --site <site> execute gris.scripts.seed.main.seed_test_data \\
        --kwargs '{"volume":"medium","only":["financeiro"]}'
    bench --site <site> execute gris.scripts.seed.main.seed_test_data \\
        --kwargs '{"dry_run":true}'

Pré-requisitos:
  1. `bench --site <site> migrate` — para garantir que fixtures
     (Roles, Carteira, ODS, etc.) estejam carregados.
  2. `apps/gris/.credentials` configurado (copie de `.credentials.example`).
"""

import frappe

from .credentials import load_credentials
from .faker_helpers import reset_seed
from .frappe_setup import seed_frappe_setup
from .modules.adultos import seed_adultos
from .modules.financeiro import seed_financeiro
from .modules.gris_core import seed_gris_core
from .modules.projetos import seed_projetos_modulo
from .volume import get_preset

VALID_MODULES = {"frappe", "gris", "financeiro", "projetos", "adultos"}


def seed_test_data(
	volume: str = "small",
	only: list[str] | None = None,
	dry_run: bool = False,
):
	"""
	Popula o site com dados de teste.

	Args:
	    volume: small | medium | large
	    only: lista de módulos a rodar; None = todos.
	          Valores válidos: 'frappe', 'gris', 'financeiro', 'projetos', 'adultos'
	    dry_run: se True, faz rollback no final (útil para validar sem persistir)
	"""
	if only:
		invalid = set(only) - VALID_MODULES
		if invalid:
			raise ValueError(f"Módulos inválidos: {invalid}. Válidos: {VALID_MODULES}")

	# Reseed Faker e random a cada execução — bench execute pode reusar processos
	# e o módulo pode não ser re-importado, então o estado do Faker persiste e
	# gera CPFs diferentes a cada run. Reset garante idempotência determinística.
	reset_seed()

	n = get_preset(volume)
	creds = load_credentials()

	print(f"\n=== SEED Gris (volume={volume}, only={only or 'todos'}, dry_run={dry_run}) ===\n")

	if not only or "frappe" in only:
		seed_frappe_setup(creds, n)
		print()

	if not only or "gris" in only:
		seed_gris_core(creds, n)
		print()

	if not only or "financeiro" in only:
		seed_financeiro(creds, n)
		print()

	if not only or "projetos" in only:
		seed_projetos_modulo(creds, n)
		print()

	if not only or "adultos" in only:
		seed_adultos(creds, n)
		print()

	if dry_run:
		frappe.db.rollback()
		print("=== DRY-RUN: rollback executado, nenhum dado persistido ===\n")
	else:
		# Script de linha de comando (bench execute/console): não há ciclo de request
		# nem worker para fechar a transação, o commit tem que ser explícito.
		frappe.db.commit()  # nosemgrep
		print("=== SEED concluído (commit) ===\n")
