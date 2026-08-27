"""Integração do GRIS com o Claude via MCP (Model Context Protocol).

- ``registry``  : catálogo de ferramentas, autorização e validação de argumentos.
- ``associados``/``financeiro``/``geral`` : implementação das ferramentas.
- ``endpoints`` : API REST (``listar_ferramentas``/``executar_ferramenta``) usada
  pelo bridge stdio em ``mcp_server/``.
- ``http``      : transporte MCP (JSON-RPC) direto sobre HTTP.

Documentação de uso: ``MCP_CLAUDE.md`` na raiz do repositório.
"""
