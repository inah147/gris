---
name: gris-skill-creator
description: Cria, evolui e valida skills para o projeto GRIS com fluxo completo de descoberta, escrita, testes, iteração e empacotamento. Use esta skill sempre que o usuário pedir para criar uma skill nova, adaptar uma skill existente, estruturar avaliação com casos de teste, comparar versões de skill, ou melhorar descrição de gatilho para ativação mais precisa.
---

# GRIS Skill Creator

## Objetivo
Esta skill orienta a criação de outras skills com qualidade de produção no contexto do repositório GRIS.

Ela cobre:
- descoberta do escopo com o usuário;
- escrita do `SKILL.md` com gatilhos claros;
- criação de recursos de apoio (`references/`, `assets/`, `scripts/`);
- execução de casos de teste e revisão humana;
- iteração até atingir qualidade satisfatória.

## Quando usar
Use quando o pedido envolver:
- "criar uma skill";
- "melhorar uma skill";
- "padronizar uma skill";
- "avaliar se a skill está funcionando";
- "otimizar descrição para skill ativar melhor".

## Princípios obrigatórios
- Priorizar linguagem PT-BR clara e objetiva.
- Descrição do frontmatter deve ser explícita sobre **quando** a skill deve ser usada.
- Evitar overfitting aos exemplos de teste.
- Não criar instruções inseguras, enganosas ou fora da intenção do usuário.
- Reutilizar padrões já existentes em `.github/skills` antes de inventar estrutura nova.

## Estrutura recomendada da skill-alvo

```text
<skill-name>/
├── SKILL.md
├── references/        (opcional)
├── assets/            (opcional)
├── scripts/           (opcional)
└── evals/             (opcional)
```

## Fluxo de criação

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
- anti-padrões;
- checklist final.

### 4) Definir avaliação
Se a skill tiver resultados verificáveis, criar `evals/evals.json` com prompts realistas.
Schema em `references/schemas.md`.

### 5) Rodar ciclo de iteração
- executar casos com e sem skill (quando aplicável);
- consolidar feedback humano;
- revisar instruções para generalizar melhor;
- repetir até qualidade estável.

### 6) Empacotar
Quando o usuário aprovar, empacotar em `.skill` usando `scripts/package_skill.py`.

## Otimização de descrição (triggering)
Quando solicitado, execute ciclo de melhoria de descrição:
1. criar conjunto de consultas que **deveriam** e **não deveriam** ativar;
2. revisar com humano;
3. iterar descrição com métrica de acerto;
4. aplicar melhor descrição ao `SKILL.md`.

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

## Checklist de entrega
- [ ] Escopo e gatilhos confirmados com o usuário.
- [ ] `SKILL.md` claro, acionável e em PT-BR.
- [ ] Casos de teste representativos definidos (quando necessário).
- [ ] Avaliação qualitativa/quantitativa registrada.
- [ ] Iterações aplicadas com base no feedback.
- [ ] Skill registrada em catálogo local (quando aplicável).
