# Evidências — régua de vencimento do registro

Spec: [docs/specs/regua-vencimento-registro/spec.md](../../specs/regua-vencimento-registro/spec.md)

## Tela de configurações (Desk)

Capturas feitas no dev.gris em 20/11/2026, com Playwright. A integração WhatsApp estava desligada.

| Arquivo | O que mostra |
|---|---|
| `configuracoes-aba-da-regua.png` | A aba "Régua de vencimento do registro". Tem o interruptor geral (desligado), a data de corte, o intervalo, os textos comuns e, para cada mensagem, um interruptor e um modelo com a lista de variáveis aceitas. O campo do grupo mostra o aviso de WhatsApp desligado na descrição, sem modal de erro (CA-07.7). |
| `pre-visualizacao-associado-30-dias.png` | A pré-visualização do aviso de 30 dias, com dados fictícios e o rodapé ("já renovado" e "mensagem automática do GRIS"). |
| `pre-visualizacao-chefe-vencidos.png` | A pré-visualização do bloco de vencidos do chefe de seção. A saudação é fixa e o rodapé aparece no fim. |

## Rodada simulada com os dados do dev.gris

A rodada usou `executar_regua("2026-11-20")` com a régua ligada e a data de corte em 01/11/2026. O
WhatsApp foi dublado e o banco voltou ao estado anterior com rollback no fim. Os números abaixo são
agregados; nenhum nome é reproduzido aqui.

| Frente | Resultado |
|---|---|
| Associado ou responsável | 82 mensagens: 76 de cobrança recorrente (quem venceu em 02/11, depois do corte) e 6 do aviso de 30 dias. Foram 49 para o próprio associado e 33 para o responsável. |
| Chefe de seção | 4 mensagens consolidadas, cobrindo 41 dos 47 beneficiários devidos. Os 6 restantes não têm chefe com telefone (métrica `sem_chefe`). |
| Resumo mensal | 1 mensagem ao grupo com os 47 beneficiários de novembro, agrupados por seção e com "Sem seção" por último, mencionando os chefes. |

A rodada encontrou um problema, já corrigido: um nome cadastrado com tratamento ("Dr. Fulano") gerava a
saudação "Olá, Dr.!". `_primeiro_nome` agora pula Dr., Dra., Sr., Sra., Srta., Prof. e Profa.

**Para a implantação:** com o corte em 01/11, a primeira rodada manda 76 cobranças recorrentes de uma
vez. Se a ideia é começar só com os próximos vencimentos, use a data da implantação como corte.
