---
applyTo: "**/*.{py,js,ts,tsx,jsx}"
description: "Use quando o pedido for corrigir erro, ajuste simples, hotfix, correção pontual ou manutenção de fluxo existente sem redesign."
---

# Ajustes simples sem retrocompatibilidade

## Objetivo
- Em correções pontuais, corrigir apenas o necessário para resolver a causa do problema atual.

## Regras
- Não criar retrocompatibilidade, fallback legado, mapeamentos de formatos antigos ou adaptações para contratos obsoletos, salvo pedido explícito do usuário.
- Preferir menor diff possível, preservando APIs e comportamento fora do escopo do bug.
- Evitar refatorações amplas, abstrações novas ou mudanças estruturais quando não forem necessárias para a correção.
- Se houver risco de quebra por falta de retrocompatibilidade, registrar de forma objetiva no resumo final.

## Critério de conclusão
- Bug corrigido no fluxo atual.
- Sem camadas extras de compatibilidade com legado.
- Sem alterações colaterais fora do escopo.
