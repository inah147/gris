#!/usr/bin/env python3
"""Gera viewer HTML estático para revisão de execuções de eval.

Uso:
  python generate_review.py <workspace_dir> --skill-name <nome> --output <arquivo.html>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

TEXT_EXTENSIONS = {".txt", ".md", ".json", ".csv", ".py", ".js", ".html", ".yaml", ".yml"}


def find_runs(workspace: Path) -> list[dict]:
    runs: list[dict] = []
    for outputs in workspace.rglob("outputs"):
        if not outputs.is_dir():
            continue
        run_dir = outputs.parent
        run_id = str(run_dir.relative_to(workspace)).replace("/", "-")

        prompt = "(No prompt found)"
        meta = run_dir / "eval_metadata.json"
        if meta.exists():
            try:
                prompt = json.loads(meta.read_text(encoding="utf-8")).get("prompt", prompt)
            except Exception:
                pass

        out_files = []
        for f in sorted(outputs.iterdir()):
            if not f.is_file():
                continue
            ext = f.suffix.lower()
            if ext in TEXT_EXTENSIONS:
                content = f.read_text(encoding="utf-8", errors="replace")
                out_files.append({"name": f.name, "type": "text", "content": content})
            else:
                out_files.append({"name": f.name, "type": "binary"})

        runs.append({"id": run_id, "prompt": prompt, "outputs": out_files})

    runs.sort(key=lambda r: r["id"])
    return runs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--skill-name", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    if not workspace.is_dir():
        raise SystemExit(f"Workspace inválido: {workspace}")

    runs = find_runs(workspace)
    if not runs:
        raise SystemExit("Nenhuma execução com outputs/ encontrada.")

    viewer = Path(__file__).parent / "viewer.html"
    template = viewer.read_text(encoding="utf-8")
    payload = json.dumps({"skill_name": args.skill_name, "runs": runs}, ensure_ascii=False)
    html = template.replace("/*__EMBEDDED_DATA__*/", f"const EMBEDDED_DATA = {payload};")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(f"Viewer gerado em: {args.output}")


if __name__ == "__main__":
    main()
