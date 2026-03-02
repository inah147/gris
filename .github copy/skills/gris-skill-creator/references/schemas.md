# Schemas JSON (GRIS Skill Creator)

Este arquivo define os formatos esperados para avaliação e benchmark de skills.

## Regras gerais
- Usar UTF-8 e JSON válido.
- Campos obrigatórios devem existir mesmo quando vazios (`[]` ou `""`).
- Manter nomes de campos exatamente como definidos aqui.

## `evals/evals.json`

```json
{
  "skill_name": "nome-da-skill",
  "evals": [
    {
      "id": 1,
      "name": "nome-curto-do-caso",
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

Notas:
- `name` é recomendado para facilitar leitura no viewer.
- `expectations` pode ficar vazio para casos qualitativos.

## `<run-dir>/eval_metadata.json`

```json
{
  "eval_id": 1,
  "eval_name": "nome-curto-do-caso",
  "prompt": "Solicitação realista do usuário",
  "expectations": [
    "Critério verificável 1"
  ],
  "configuration": "with_skill"
}
```

`configuration` recomendado: `with_skill`, `without_skill` ou `old_skill`.

## `<run-dir>/grading.json`

```json
{
  "expectations": [
    {
      "text": "Critério A",
      "passed": true,
      "evidence": "Prova objetiva"
    }
  ],
  "summary": {
    "passed": 1,
    "failed": 0,
    "total": 1,
    "pass_rate": 1.0
  },
  "notes": []
}
```

Importante: o viewer depende dos campos `text`, `passed`, `evidence`.

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
    "configs": ["with_skill", "without_skill"],
    "runs_count": 4
  },
  "runs": [
    {
      "run_id": "eval-1-with_skill",
      "eval_id": 1,
      "eval_name": "nome-curto-do-caso",
      "configuration": "with_skill",
      "summary": {
        "passed": 2,
        "failed": 0,
        "total": 2,
        "pass_rate": 1.0,
        "time_seconds": 31.2,
        "tokens": 2800
      },
      "expectations": [
        {"text": "Critério A", "passed": true, "evidence": "..."}
      ],
      "notes": []
    }
  ],
  "run_summary": {
    "with_skill": {
      "pass_rate": {"mean": 0.8, "min": 0.7, "max": 0.9},
      "time_seconds": {"mean": 31.2, "min": 29.5, "max": 34.0},
      "tokens": {"mean": 2800, "min": 2500, "max": 3200}
    },
    "without_skill": {
      "pass_rate": {"mean": 0.5, "min": 0.4, "max": 0.6},
      "time_seconds": {"mean": 22.0, "min": 20.5, "max": 24.1},
      "tokens": {"mean": 1800, "min": 1500, "max": 2100}
    },
    "delta": {
      "pass_rate": 0.3,
      "time_seconds": 9.2,
      "tokens": 1000
    }
  },
  "analysis_notes": []
}
```

## `comparison.json` (opcional)

```json
{
  "winner": "A",
  "reasoning": "Resumo da comparação cega",
  "scores": {
    "A": 8.5,
    "B": 7.0
  },
  "rubric": [
    {
      "criterion": "Correção",
      "A": 9,
      "B": 7,
      "notes": "A cobriu todos os requisitos"
    }
  ]
}
```

## `feedback.json` (viewer)

```json
{
  "reviews": [
    {
      "run_id": "eval-1-with_skill",
      "feedback": "Está bom, mas faltou validação de permissão.",
      "timestamp": "2026-03-02T12:00:00Z"
    }
  ],
  "status": "complete"
}
```
