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


def read_json(path: Path) -> dict | list | None:
	if not path.exists():
		return None
	try:
		return json.loads(path.read_text(encoding="utf-8"))
	except Exception:
		return None


def infer_configuration(run_dir: Path) -> str:
	relative = "-".join(run_dir.parts).lower()
	if "without_skill" in relative:
		return "without_skill"
	if "old_skill" in relative:
		return "old_skill"
	if "with_skill" in relative:
		return "with_skill"
	return "with_skill"


def find_runs(workspace: Path) -> list[dict]:
	runs: list[dict] = []
	for outputs in workspace.rglob("outputs"):
		if not outputs.is_dir():
			continue
		run_dir = outputs.parent
		run_id = str(run_dir.relative_to(workspace)).replace("/", "-")

		prompt = "(No prompt found)"
		meta = run_dir / "eval_metadata.json"
		meta_payload = read_json(meta)
		if isinstance(meta_payload, dict):
			prompt = str(meta_payload.get("prompt", prompt))
			eval_name = str(meta_payload.get("eval_name", run_id))
			configuration = str(meta_payload.get("configuration", infer_configuration(run_dir)))
		else:
			eval_name = run_id
			configuration = infer_configuration(run_dir)

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

		grading_payload = read_json(run_dir / "grading.json")
		grading_expectations = []
		grading_summary = {}
		if isinstance(grading_payload, dict):
			grading_expectations = grading_payload.get("expectations", []) or []
			grading_summary = grading_payload.get("summary", {}) or {}

		runs.append(
			{
				"id": run_id,
				"prompt": prompt,
				"eval_name": eval_name,
				"configuration": configuration,
				"outputs": out_files,
				"grading": {
					"expectations": grading_expectations,
					"summary": grading_summary,
				},
			}
		)

	runs.sort(key=lambda r: r["id"])
	return runs


def index_previous_outputs(previous_workspace: Path | None) -> dict[str, dict]:
	if previous_workspace is None:
		return {}

	runs = find_runs(previous_workspace)
	indexed: dict[str, dict] = {}
	for run in runs:
		key = f"{run.get('eval_name', '')}::{run.get('configuration', '')}"
		indexed[key] = {
			"outputs": run.get("outputs", []),
			"grading": run.get("grading", {}),
		}
	return indexed


def index_previous_feedback(previous_workspace: Path | None) -> dict[str, str]:
	if previous_workspace is None:
		return {}

	feedback_payload = read_json(previous_workspace / "feedback.json")
	if not isinstance(feedback_payload, dict):
		return {}

	reviews = feedback_payload.get("reviews", [])
	if not isinstance(reviews, list):
		return {}

	result: dict[str, str] = {}
	for review in reviews:
		if not isinstance(review, dict):
			continue
		run_id = review.get("run_id")
		feedback = review.get("feedback")
		if isinstance(run_id, str) and isinstance(feedback, str):
			result[run_id] = feedback
	return result


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("workspace", type=Path)
	parser.add_argument("--skill-name", required=True)
	parser.add_argument("--output", type=Path, required=True)
	parser.add_argument("--benchmark", type=Path, help="Caminho para benchmark.json")
	parser.add_argument("--previous-workspace", type=Path, help="Workspace da iteração anterior")
	args = parser.parse_args()

	workspace = args.workspace.resolve()
	if not workspace.is_dir():
		raise SystemExit(f"Workspace inválido: {workspace}")

	runs = find_runs(workspace)
	if not runs:
		raise SystemExit("Nenhuma execução com outputs/ encontrada.")

	previous_workspace = args.previous_workspace.resolve() if args.previous_workspace else None
	if previous_workspace and not previous_workspace.is_dir():
		raise SystemExit(f"Workspace anterior inválido: {previous_workspace}")

	previous_outputs = index_previous_outputs(previous_workspace)
	previous_feedback = index_previous_feedback(previous_workspace)

	for run in runs:
		key = f"{run.get('eval_name', '')}::{run.get('configuration', '')}"
		run["previous"] = previous_outputs.get(key, {"outputs": [], "grading": {}})
		run["previous_feedback"] = previous_feedback.get(run["id"], "")

	benchmark = None
	if args.benchmark:
		benchmark = read_json(args.benchmark.resolve())
	else:
		benchmark = read_json(workspace / "benchmark.json")

	viewer = Path(__file__).parent / "viewer.html"
	template = viewer.read_text(encoding="utf-8")
	payload = json.dumps(
		{
			"skill_name": args.skill_name,
			"runs": runs,
			"benchmark": benchmark if isinstance(benchmark, dict) else None,
		},
		ensure_ascii=False,
	)
	html = template.replace("/*__EMBEDDED_DATA__*/", f"const EMBEDDED_DATA = {payload};")

	args.output.parent.mkdir(parents=True, exist_ok=True)
	args.output.write_text(html, encoding="utf-8")
	print(f"Viewer gerado em: {args.output}")


if __name__ == "__main__":
	main()
