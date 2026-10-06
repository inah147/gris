"""Portal de acessos: catálogo, solicitações, aprovação e concessão.

Três tipos de acesso convivem aqui, cada um com a sua fonte de verdade:

* **Papel do Gris** — as linhas de ``Has Role`` do usuário. A concessão é automática.
* **Drive compartilhado** — o Single ``Configuracoes Google Workspace`` e os jobs de
  ``gris.api.google_workspace.access_manager``. O portal não muda esse mecanismo: só lê
  o Single e acrescenta concessões manuais pelo mesmo caminho que o Desk usa.
* **Ferramenta externa** (Canva, Microsoft 365) — sem API disponível; a ``Licenca de
  Ferramenta`` controla quem ocupa cada vaga e a equipe cria a conta à mão, sempre com o
  id@escoteiros.
"""
