---
name: gris-skill-creator
description: Cria, evolui e valida skills para o projeto GRIS/Frappe. Use sempre que o usuário pedir para criar skill nova, ajustar skill existente, padronizar SKILL.md, definir casos de teste, comparar versões de skill, ou estruturar revisão humana com benchmark de qualidade.
---

# GRIS Skill Creator

## Objetivo
Esta skill orienta a criação de outras skills com qualidade de produção no contexto GRIS/Frappe.

Ela cobre ponta a ponta:
- descoberta de escopo e critérios de sucesso;
- escrita/edição do `SKILL.md` com gatilhos claros;
- definição de `evals/evals.json` com prompts realistas;
- execução e avaliação (`grading.json`, `benchmark.json`);
- revisão humana via viewer HTML;
- iteração até estabilidade.

## Quando usar
Use quando o pedido envolver:
- "criar uma skill";
- "melhorar uma skill";
- "padronizar uma skill";
- "avaliar se a skill está funcionando";
- "comparar duas versões de skill";
- "otimizar descrição para skill ativar melhor".

## Progressive Disclosure
Use carregamento progressivo para reduzir contexto e manter foco:
1. **Metadata** (`name` + `description`) para triggering.
2. **Corpo do `SKILL.md`** para execução do fluxo.
3. **Recursos sob demanda** (`references/`, `agents/`, `scripts/`, `assets/`).

Se o `SKILL.md` ficar grande, mova detalhes para `references/` e deixe ponteiros explícitos de quando cada arquivo deve ser lido.

## Princípios obrigatórios
- Priorizar linguagem PT-BR clara e objetiva.
- Frontmatter deve explicitar **quando ativar** e **o que entrega**.
- Evitar overfitting aos exemplos de teste.
- Não criar instruções inseguras, enganosas ou fora da intenção do usuário.
- Reutilizar padrões já existentes em `.github/skills` antes de inventar estrutura nova.
- Para tarefas de Frappe, sempre considerar permissões, validação no backend e risco de N+1.

## Estrutura recomendada da skill-alvo

```text
<skill-name>/
├── SKILL.md
├── references/        (opcional)
├── assets/            (opcional)
├── scripts/           (opcional)
└── evals/             (opcional)
```

## Fluxo operacional (versão intermediária)

### 1) Capturar intenção
Pergunte e confirme:
1. O que a skill deve habilitar?
2. Em quais situações deve ativar?
3. Qual formato de saída esperado?
4. Quais restrições (stack, segurança, estilo, idioma)?

### 2) Entrevista técnica curta
Levante:
- edge cases;
- entradas/saídas reais;
- critérios de sucesso;
- exemplos positivos e negativos.

### 3) Escrever o `SKILL.md`
Inclua:
- frontmatter (`name`, `description`);
- seção "Quando usar";
- fluxo operacional recomendado;
- seção de anti-padrões;
- anti-padrões;
- checklist final.

### 4) Definir avaliação
Se a skill tiver resultados verificáveis:
- criar `evals/evals.json` com prompts realistas;
- incluir expectativas objetivas quando aplicável;
- seguir schema em `references/schemas.md`.

### 5) Rodar ciclo de iteração
- executar casos com e sem skill (ou com skill antiga, quando for melhoria);
- gerar `grading.json` por execução;
- agregar `benchmark.json`;
- consolidar feedback humano no viewer;
- revisar instruções para generalizar melhor;
- repetir até qualidade estável.

### 6) Empacotar
Quando o usuário aprovar, empacotar em `.skill` usando `scripts/package_skill.py`.

## Comparação cega (opcional)
Use quando o usuário pedir rigor extra entre duas versões de saída.

- Ler `agents/comparator.md` para formato de comparação.
- Ler `agents/analyzer.md` para análise de padrões após comparação.

## Otimização de descrição (opcional)
Use quando o usuário pedir melhoria de triggering.

1. criar conjunto de consultas que **deveriam** e **não deveriam** ativar;
2. revisar com humano via template em `assets/eval_review.html`;
3. iterar descrição com métricas de acerto;
4. aplicar melhor descrição ao frontmatter.

## Compatibilidade com GRIS/Frappe
- Priorizar validações críticas no backend (não só no client).
- Incluir critérios de autorização e segurança nos casos de teste quando houver mutação de dados.
- Evitar instruções que incentivem SQL inseguro, `ignore_permissions=True` sem contexto, ou padrões com N+1.

## Recursos desta skill
- Agentes especializados:
  - `agents/grader.md`
  - `agents/comparator.md`
  - `agents/analyzer.md`
- Schemas:
  - `references/schemas.md`
- Scripts utilitários:
  - `scripts/quick_validate.py`
  - `scripts/aggregate_benchmark.py`
  - `scripts/package_skill.py`
- Viewer:
  - `eval-viewer/generate_review.py`
  - `eval-viewer/viewer.html`
- Template de revisão de gatilhos:
  - `assets/eval_review.html`

## Checklist de entrega
- [ ] Escopo e gatilhos confirmados com o usuário.
- [ ] `SKILL.md` claro, acionável e em PT-BR.
- [ ] Casos de teste representativos definidos (quando necessário).
- [ ] Avaliação qualitativa/quantitativa registrada.
- [ ] Iterações aplicadas com base no feedback.
- [ ] Riscos Frappe (permissão, segurança, performance) cobertos nos critérios.
- [ ] Skill registrada em catálogo local (quando aplicável).
