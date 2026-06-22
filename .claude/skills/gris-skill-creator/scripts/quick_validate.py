#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_json(path: Path) -> dict:
	try:
		return json.loads(path.read_text(encoding="utf-8"))
	except FileNotFoundError:
		raise SystemExit(f"Arquivo não encontrado: {path}")
	except json.JSONDecodeError as exc:
		raise SystemExit(f"JSON inválido em {path}: {exc}")


def validate_skill(skill_dir: Path) -> list[str]:
	errors: list[str] = []
	skill_md = skill_dir / "SKILL.md"
	if not skill_md.exists():
		errors.append("SKILL.md ausente")

	evals_path = skill_dir / "evals" / "evals.json"
	if evals_path.exists():
		payload = load_json(evals_path)
		if not isinstance(payload.get("skill_name"), str) or not payload["skill_name"].strip():
			errors.append("evals/evals.json: 'skill_name' ausente ou inválido")

		evals = payload.get("evals")
		if not isinstance(evals, list) or not evals:
			errors.append("evals/evals.json: 'evals' deve ser lista não vazia")
		else:
			for index, item in enumerate(evals, start=1):
				if not isinstance(item, dict):
					errors.append(f"evals/evals.json: item {index} não é objeto")
					continue

				for field in ("id", "prompt", "expected_output", "files"):
					if field not in item:
						errors.append(f"evals/evals.json: item {index} sem campo obrigatório '{field}'")

				if "expectations" in item and not isinstance(item["expectations"], list):
					errors.append(f"evals/evals.json: item {index} com 'expectations' inválido")

	return errors


def main() -> None:
	parser = argparse.ArgumentParser(description="Validação rápida de skill")
	parser.add_argument("skill_dir", type=Path, help="Diretório da skill")
	args = parser.parse_args()

	skill_dir = args.skill_dir.resolve()
	if not skill_dir.is_dir():
		raise SystemExit(f"Diretório inválido: {skill_dir}")

	errors = validate_skill(skill_dir)
	if errors:
		print("❌ Falhas de validação:")
		for error in errors:
			print(f"- {error}")
		raise SystemExit(1)

	print("✅ Validação concluída sem erros")


if __name__ == "__main__":
	main()
