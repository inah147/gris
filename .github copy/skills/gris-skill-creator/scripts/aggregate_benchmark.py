#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean


def load_json(path: Path) -> dict:
	return json.loads(path.read_text(encoding="utf-8"))


def safe_mean(values: list[float | int]) -> float:
	return float(mean(values)) if values else 0.0


def collect_runs(iteration_dir: Path) -> list[dict]:
	runs: list[dict] = []
	for outputs_dir in iteration_dir.rglob("outputs"):
		run_dir = outputs_dir.parent
		run_id = str(run_dir.relative_to(iteration_dir)).replace("/", "-")

		eval_meta_path = run_dir / "eval_metadata.json"
		grading_path = run_dir / "grading.json"
		timing_path = run_dir / "timing.json"

		if not eval_meta_path.exists() or not grading_path.exists():
			continue

		meta = load_json(eval_meta_path)
		grading = load_json(grading_path)
		timing = load_json(timing_path) if timing_path.exists() else {}

		summary = grading.get("summary", {})
		expectations = grading.get("expectations", [])

		runs.append(
			{
				"run_id": run_id,
				"eval_id": meta.get("eval_id"),
				"eval_name": meta.get("eval_name", f"eval-{meta.get('eval_id', 'unknown')}"),
				"configuration": meta.get("configuration", "with_skill"),
				"summary": {
					"passed": int(summary.get("passed", 0)),
					"failed": int(summary.get("failed", 0)),
					"total": int(summary.get("total", 0)),
					"pass_rate": float(summary.get("pass_rate", 0.0)),
					"time_seconds": float(timing.get("total_duration_seconds", 0.0)),
					"tokens": int(timing.get("total_tokens", 0)),
				},
				"expectations": expectations,
				"notes": grading.get("notes", []),
			}
		)

	return sorted(runs, key=lambda run: run["run_id"])


def summarize_by_configuration(runs: list[dict]) -> dict:
	grouped: dict[str, list[dict]] = {}
	for run in runs:
		grouped.setdefault(run["configuration"], []).append(run)

	summary: dict[str, dict] = {}
	for config, config_runs in grouped.items():
		pass_rates = [run["summary"]["pass_rate"] for run in config_runs]
		times = [run["summary"].get("time_seconds", 0.0) for run in config_runs]
		tokens = [run["summary"].get("tokens", 0) for run in config_runs]

		summary[config] = {
			"pass_rate": {
				"mean": safe_mean(pass_rates),
				"min": min(pass_rates) if pass_rates else 0.0,
				"max": max(pass_rates) if pass_rates else 0.0,
			},
			"time_seconds": {
				"mean": safe_mean(times),
				"min": min(times) if times else 0.0,
				"max": max(times) if times else 0.0,
			},
			"tokens": {
				"mean": safe_mean(tokens),
				"min": min(tokens) if tokens else 0,
				"max": max(tokens) if tokens else 0,
			},
		}

	if "with_skill" in summary:
		baseline_key = (
			"without_skill" if "without_skill" in summary else "old_skill" if "old_skill" in summary else None
		)
		if baseline_key:
			summary["delta"] = {
				"pass_rate": round(
					summary["with_skill"]["pass_rate"]["mean"] - summary[baseline_key]["pass_rate"]["mean"], 4
				),
				"time_seconds": round(
					summary["with_skill"]["time_seconds"]["mean"]
					- summary[baseline_key]["time_seconds"]["mean"],
					4,
				),
				"tokens": round(
					summary["with_skill"]["tokens"]["mean"] - summary[baseline_key]["tokens"]["mean"]
				),
			}

	return summary


def main() -> None:
	parser = argparse.ArgumentParser(description="Agrega resultados em benchmark.json")
	parser.add_argument("iteration_dir", type=Path, help="Diretório da iteração")
	parser.add_argument("--skill-name", required=True, help="Nome da skill")
	parser.add_argument(
		"--output", type=Path, help="Arquivo de saída (default: <iteration_dir>/benchmark.json)"
	)
	args = parser.parse_args()

	iteration_dir = args.iteration_dir.resolve()
	if not iteration_dir.is_dir():
		raise SystemExit(f"Diretório inválido: {iteration_dir}")

	runs = collect_runs(iteration_dir)
	if not runs:
		raise SystemExit("Nenhum run válido encontrado (esperado: eval_metadata.json + grading.json)")

	payload = {
		"metadata": {
			"skill_name": args.skill_name,
			"timestamp": datetime.now(timezone.utc).isoformat(),
			"configs": sorted({run["configuration"] for run in runs}),
			"runs_count": len(runs),
		},
		"runs": runs,
		"run_summary": summarize_by_configuration(runs),
		"analysis_notes": [],
	}

	output = args.output.resolve() if args.output else (iteration_dir / "benchmark.json")
	output.parent.mkdir(parents=True, exist_ok=True)
	output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
	print(f"benchmark.json gerado em: {output}")


if __name__ == "__main__":
	main()
