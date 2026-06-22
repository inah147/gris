#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tarfile
from pathlib import Path

IGNORED = {
	"__pycache__",
	".DS_Store",
	".git",
}


def is_ignored(path: Path) -> bool:
	return any(part in IGNORED for part in path.parts)


def main() -> None:
	parser = argparse.ArgumentParser(description="Empacota uma skill em .skill")
	parser.add_argument("skill_dir", type=Path, help="Diretório da skill")
	parser.add_argument("--output", type=Path, help="Arquivo de saída .skill")
	args = parser.parse_args()

	skill_dir = args.skill_dir.resolve()
	if not skill_dir.is_dir():
		raise SystemExit(f"Diretório inválido: {skill_dir}")

	if not (skill_dir / "SKILL.md").exists():
		raise SystemExit("SKILL.md não encontrado no diretório informado")

	output = args.output.resolve() if args.output else skill_dir.with_suffix(".skill")
	output.parent.mkdir(parents=True, exist_ok=True)

	with tarfile.open(output, "w:gz") as archive:
		for file_path in sorted(skill_dir.rglob("*")):
			if not file_path.is_file() or is_ignored(file_path):
				continue
			archive.add(file_path, arcname=file_path.relative_to(skill_dir.parent))

	print(f"Pacote gerado: {output}")


if __name__ == "__main__":
	main()
