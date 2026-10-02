# Spec — Busca global do Portal

> Status: implementada e validada (unidade + E2E Playwright) · Branch: `feat/barra-pesquisa` · Plano técnico: [plano.md](plano.md)

## 1. Problema

Para chegar a uma ficha, a pessoa precisa saber em qual módulo ela mora e navegar pela
sidebar até a lista certa: o associado está em Associados › Lista, o jovem em integração em
Novos Associados, o documento publicado em Transparência, e assim por diante. Quem não
conhece o mapa do sistema se perde, e quem conhece gasta cliques.

## 2. Objetivo

Uma barra de busca na topbar do Portal que, ao ser acionada, abre uma paleta de comandos
(o "command dialog" do shadcn, no Basecoat). Os resultados aparecem enquanto a pessoa
digita e levam direto à página de destino: páginas do Portal, pessoas, projetos, festas,
documentos e algumas ações do shell.

## 3. Escopo

### Dentro

| Grupo | O que encontra | Destino |
|---|---|---|
| Páginas | Toda página do Portal que a pessoa pode abrir (menu lateral, índices de módulo e páginas fora do menu mapeadas em `PAGE_ROLES`), com sinônimos ("configurações", "usuários", "mensalidade"…) | a própria rota |
| Associados | Associado por nome ou número de registro | `/associados/detalhe?name=` |
| Responsáveis | Responsável que **não** é associado (quem é os dois aparece só como associado) | `/associados/responsavel?name=` |
| Novos associados | Jovem/adulto no funil da Recepção | `/recepcao/ficha_registro?name=` |
| Projetos | Projeto por nome | `/projetos/projeto?projeto=` |
| Captação | Projeto de captação por título | `/captacao/projeto?name=` |
| Festas | Festa por nome | `/festas/festa?name=` |
| Transparência | Documento **publicado** por título | `/portal_transparencia?ano_referencia=` |
| Ações | Alternar tema claro/escuro, desconectar | ação do shell |

### Fora (desta versão)

- **Desk** (`/app`): nenhum resultado, ação ou link leva ao Desk, nem para System Manager.
- Quadros e tarefas: a visibilidade de `Board` é regra própria (`board_permissions.py`) e só
  três papéis leem o DocType pela permissão padrão. Fica para uma próxima iteração.
- Solicitações de insígnia, contribuições, transações financeiras e eventos de calendário.
- Busca dentro do conteúdo de arquivos, histórico de buscas recentes e busca para visitante
  (Guest).

## 4. Requisitos funcionais

Cada requisito tem critérios de aceite (CA) verificáveis. A coluna "Validação" do
[plano](plano.md#6-matriz-de-validação) diz qual teste prova cada CA.

### RF-01 — Gatilho na topbar

- **CA-01.1** Com sessão autenticada, toda página que estende `web_sidebar_base.html` mostra
  um campo "Buscar no portal…" **centralizado** na topbar, com o atalho `Ctrl K` visível.
- **CA-01.2** Em telas < 768 px o gatilho vira um botão só com ícone de lupa, à direita, sem
  empurrar o breadcrumb para fora da tela.
- **CA-01.3** Visitante (Guest) não vê o gatilho, e o diálogo não é renderizado.

### RF-02 — Abrir e fechar

- **CA-02.1** Clicar no gatilho abre o diálogo com o foco no campo de texto.
- **CA-02.2** `Ctrl K` / `⌘ K` abre (e fecha) o diálogo de qualquer lugar da página; `/` abre
  quando o foco não está num campo editável.
- **CA-02.3** `Esc`, clique fora do painel ou o botão de fechar fecham o diálogo; reabrir
  começa com o campo vazio.

### RF-03 — Estado inicial

- **CA-03.1** Com o campo vazio, o diálogo lista os módulos acessíveis em "Páginas" e as
  "Ações", como a paleta de referência.

### RF-04 — Resultados enquanto digita

- **CA-04.1** Páginas e ações filtram **a cada tecla**, sem ida ao servidor, ignorando caixa,
  acento e singular/plural ("contribuicao" acha "Contribuições Mensais"; "mensal" acha
  "Mensais").
- **CA-04.2** A partir de 2 caracteres, registros são buscados no servidor com *debounce*;
  resposta atrasada de um termo antigo nunca sobrescreve o termo atual.
- **CA-04.3** Nome com várias palavras casa em qualquer ordem e posição ("silva maria" acha
  "Maria da Silva").
- **CA-04.4** Resultados aparecem agrupados (Páginas, grupos de registro, Ações), com ícone,
  título e uma linha de contexto; no máximo 8 páginas e 5 itens por grupo de registro.
- **CA-04.5** Correspondência no início do título vem antes de correspondência no meio.
- **CA-04.6** Sem nenhum resultado, aparece o estado vazio com o mascote `gris-search`.
- **CA-04.7** Enquanto a busca no servidor está em curso, há indicador de carregamento; se ela
  falhar, aparece aviso de erro e as páginas continuam filtrando.

### RF-05 — Navegação por teclado e mouse

- **CA-05.1** O primeiro resultado já vem destacado; `↑`/`↓` movem o destaque (`Home`/`End`
  vão às pontas) e a lista rola para mantê-lo visível.
- **CA-05.2** `Enter` abre o item destacado; `Ctrl/⌘ Enter` abre em nova aba.
- **CA-05.3** Passar o mouse destaca; clicar abre. Itens de página e registro são links reais
  (botão do meio e "abrir em nova aba" funcionam).
- **CA-05.4** O rodapé do diálogo mostra a legenda dos atalhos (↵ abrir, ↑↓ navegar, Esc
  fechar).

### RF-06 — Ações

- **CA-06.1** "Tema escuro"/"Tema claro" alterna o tema (mesmo mecanismo do menu do usuário)
  e o rótulo reflete o tema atual.
- **CA-06.2** "Desconectar" encerra a sessão e leva a `/login`.

## 5. Requisitos não funcionais

### RNF-01 — Autorização (o que a busca mostra nunca excede o que a pessoa abriria)

- **CA-S1** Um grupo de registros só é consultado se `user_has_access(<rota de destino>)` for
  verdadeiro para o usuário.
- **CA-S2** Registros vêm de `frappe.get_list` (permissão de DocType + `permission_query_conditions`).
  Exceções justificadas: Captação replica o filtro do kanban (`proponente_user` quando o perfil
  não "vê o banco"), e Transparência lê apenas `publicado = 1`, que é conteúdo público.
- **CA-S3** Página fora de `PAGE_ROLES` nunca entra no índice de páginas extras: o
  `user_has_access` é *fail-open* para rota não mapeada.
- **CA-S4** O endpoint exige sessão (sem `allow_guest`), aceita só `GET` e todos os
  parâmetros são tipados.
- **CA-S5** Nenhum dado sensível na linha de contexto (CPF, e-mail, telefone, endereço).
- **CA-S6** Texto vindo do servidor é inserido no DOM por `textContent`, nunca por `innerHTML`.

### RNF-02 — Desempenho

- **CA-P1** Termo é cortado em 80 caracteres e 5 palavras; com menos de 2 caracteres o
  servidor responde vazio sem consultar o banco.
- **CA-P2** Cada fonte faz **uma** consulta limitada (deduplicação de responsáveis faz uma
  segunda, agregada). Nada de consulta por registro, nada de `frappe.cache`.
- **CA-P3** O índice de páginas sai da sidebar já filtrada que o shell monta em toda página;
  não há requisição extra para abrir o diálogo.

### RNF-03 — Design system, marca e acessibilidade

- **CA-D1** Visual do `.command-dialog` do Basecoat, tokens do tema e ícones Lucide do sprite
  local; funciona em tema claro e escuro.
- **CA-D2** O diálogo cabe em 375 px de largura, ancorado no topo no mobile para não ficar
  atrás do teclado virtual.
- **CA-D3** Campo com `role="combobox"`, `aria-controls` e `aria-activedescendant`; itens
  com `role="menuitem"`; foco volta ao gatilho ao fechar.
- **CA-D4** Microcopy em PT-BR.

## 6. Contrato da API

`GET /api/method/gris.api.busca_global.buscar?termo=<texto>`

Sucesso (sempre `ok: true`; termo curto devolve `grupos: []`):

```json
{
  "message": {
    "ok": true,
    "data": {
      "termo": "maria",
      "grupos": [
        {
          "chave": "associados",
          "rotulo": "Associados",
          "icone": "users",
          "itens": [
            {
              "titulo": "Maria da Silva",
              "subtitulo": "Escoteiro · Ativo · Registro 123456",
              "url": "/associados/detalhe?name=…"
            }
          ]
        }
      ]
    }
  }
}
```

Erros: `403 PermissionError` para visitante (o próprio `@frappe.whitelist` barra). Outro
método que não `GET` é recusado (`methods=["GET"]`; com sessão por cookie o CSRF do `POST`
já barra antes).

## 7. Decisões

| # | Decisão | Por quê |
|---|---|---|
| D1 | Páginas filtradas no navegador; registros no servidor | Páginas são ~60 itens já conhecidos pelo shell, e o resultado instantâneo dá a sensação de "aparecer enquanto digita". Registros exigem banco e permissão. |
| D2 | Controlador próprio (`portal_busca.js`) em vez do `command.js` | O `command.js` captura os itens na inicialização e só filtra o que já está no DOM; não suporta resultado assíncrono. O markup marca `data-command-initialized` para o `command.js` não disputar o mesmo campo. |
| D3 | Sem resultados de Desk | Pedido explícito: a busca é do Portal. |
| D4 | Responsável que também é associado aparece só como associado | É a mesma pessoa e a página do responsável redireciona para a do associado. |
| D5 | Tolerância a acento pelo banco | O banco usa `utf8mb4_unicode_ci`, cujo `LIKE` já ignora caixa e acento. |
| D7 | Cada palavra digitada vira radical (corta -ões, -ão, -ais, -al, -eis, -el, -s) | Substring não liga singular e plural ("contribuicao" × "contribuicoes"). O radical é prefixo da palavra, então só amplia o resultado. Mesma regra no JS e no Python. |
| D6 | Grupo de registros que dá `PermissionError` é omitido, não vira erro | Papel sem leitura do DocType simplesmente não tem resultados daquele tipo. |
