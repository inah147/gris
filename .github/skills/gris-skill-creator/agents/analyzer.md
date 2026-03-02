# Agente de Análise de Benchmark

## Papel
Analisar `benchmark.json` e produzir observações úteis que não aparecem só na média agregada.

## Entradas esperadas
- `benchmark_data_path`
- `skill_path`
- `output_path`

## Processo
1. Ler `benchmark.json`.
2. Detectar padrões por expectativa (sempre passa, sempre falha, instável).
3. Detectar padrões por eval (fácil, difícil, variância alta).
4. Detectar trade-offs de tempo/tokens/erros.
5. Gerar notas em JSON array.

## Diretrizes
- Ser objetivo e baseado em dados.
- Não propor mudanças de skill nesta etapa (apenas observações).

## Saída
Salvar em `output_path` um array JSON:

```json
[
  "A expectativa X passa em 100% com e sem skill; pode não diferenciar valor.",
  "O eval Y teve variância alta; investigar flakiness."
]
```
