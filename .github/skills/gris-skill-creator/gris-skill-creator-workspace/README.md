# Gris Skill Creator Workspace

Este workspace foi preparado para avaliação da `gris-skill-creator`.

## Estrutura
- `iteration-1/eval-<id>/with_skill/outputs/`
- `iteration-1/eval-<id>/without_skill/outputs/`

## Próximos passos
1. Execute cada prompt de `evals/evals.json` em duas configurações:
   - `with_skill`: usando esta skill
   - `without_skill`: baseline sem skill (ou skill antiga, se preferir)
2. Salve os artefatos finais em `outputs/`.
3. Gere `grading.json` e `timing.json` para cada run.
4. Agregue benchmark:
   - `/workspace/frappe-bench/env/bin/python scripts/aggregate_benchmark.py gris-skill-creator-workspace/iteration-1 --skill-name gris-skill-creator`
5. Gere review HTML:
   - `/workspace/frappe-bench/env/bin/python eval-viewer/generate_review.py gris-skill-creator-workspace/iteration-1 --skill-name gris-skill-creator --output gris-skill-creator-workspace/iteration-1/review.html`
