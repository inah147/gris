# Schemas JSON (GRIS Skill Creator)

Este arquivo define os formatos esperados para avaliação e benchmark de skills.

## `evals/evals.json`

```json
{
  "skill_name": "nome-da-skill",
  "evals": [
    {
      "id": 1,
      "prompt": "Solicitação realista do usuário",
      "expected_output": "Descrição do resultado esperado",
      "files": [],
      "expectations": [
        "Critério verificável 1",
        "Critério verificável 2"
      ]
    }
  ]
}
```

## `<run-dir>/grading.json`

```json
{
  "expectations": [
    {"text": "Critério A", "passed": true, "evidence": "Prova objetiva"}
  ],
  "summary": {"passed": 1, "failed": 0, "total": 1, "pass_rate": 1.0},
  "execution_metrics": {
    "total_tool_calls": 10,
    "total_steps": 4,
    "errors_encountered": 0,
    "output_chars": 2000,
    "transcript_chars": 1200
  },
  "timing": {"total_duration_seconds": 24.5}
}
```

> Importante: o viewer espera os campos `text`, `passed`, `evidence` exatamente nesses nomes.

## `<run-dir>/timing.json`

```json
{
  "total_tokens": 12345,
  "duration_ms": 23332,
  "total_duration_seconds": 23.3
}
```

## `benchmark.json`

```json
{
  "metadata": {
    "skill_name": "nome-da-skill",
    "timestamp": "2026-03-02T12:00:00Z",
    "evals_run": [1, 2],
    "runs_per_configuration": 3
  },
  "runs": [
    {
      "eval_id": 1,
      "configuration": "with_skill",
      "run_number": 1,
      "result": {
        "pass_rate": 0.8,
        "passed": 4,
        "failed": 1,
        "total": 5,
        "time_seconds": 31.2,
        "tokens": 2800,
        "errors": 0
      },
      "expectations": [
        {"text": "Critério A", "passed": true, "evidence": "..."}
      ],
      "notes": []
    }
  ],
  "run_summary": {
    "with_skill": {
      "pass_rate": {"mean": 0.8, "stddev": 0.1, "min": 0.7, "max": 0.9},
      "time_seconds": {"mean": 31.2, "stddev": 2.1, "min": 29.5, "max": 34.0},
      "tokens": {"mean": 2800, "stddev": 300, "min": 2500, "max": 3200}
    },
    "without_skill": {
      "pass_rate": {"mean": 0.5, "stddev": 0.1, "min": 0.4, "max": 0.6},
      "time_seconds": {"mean": 22.0, "stddev": 1.4, "min": 20.5, "max": 24.1},
      "tokens": {"mean": 1800, "stddev": 200, "min": 1500, "max": 2100}
    },
    "delta": {"pass_rate": "+0.30", "time_seconds": "+9.2", "tokens": "+1000"}
  },
  "notes": []
}
```

## `comparison.json` (opcional)

```json
{
  "winner": "A",
  "reasoning": "Resumo da comparação cega",
  "rubric": {},
  "output_quality": {}
}
```
