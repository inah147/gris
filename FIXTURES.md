# Guia de Fixtures - Gris

## O que são Fixtures?

Fixtures são dados de configuração que você quer versionar junto com o código do seu app. Exemplos:
- Roles (funções de usuário)
- Role Profiles (perfis de função)
- Custom Fields (campos personalizados)
- Workflow States (estados de workflow)
- Doctypes customizados de configuração

## Como Exportar Fixtures

### 1. Exportar TODAS as fixtures configuradas

```bash
cd /workspace/frappe-bench
bench --site dev.gris export-fixtures
```

Isso exporta todos os doctypes listados em `gris/hooks.py` na seção `fixtures`.

### 2. Exportar um Doctype específico

```bash
bench --site dev.gris export-fixtures --app gris --doctype "Role"
```

### 3. Exportar com filtros

Você já tem isso configurado no `hooks.py`. Por exemplo, para exportar apenas roles específicas:

```python
{
    "dt": "Role",
    "filters": [
        ["name", "in", [
            "Gestor de Associados",
            "Visualizador Associados"
        ]]
    ]
}
```

## Como Adicionar Novas Fixtures

### Opção 1: Adicionar no hooks.py

Edite `gris/hooks.py` e adicione na lista `fixtures`:

```python
fixtures = [
    # ... fixtures existentes ...
    {
        "dt": "Custom Field",
        "filters": [
            ["dt", "=", "User"]
        ]
    },
    {
        "dt": "Workflow State"
    }
]
```

### Opção 2: Exportar um registro específico

```bash
bench --site dev.gris export-fixtures --app gris --doctype "Custom Field" --filters '[["dt", "=", "User"]]'
```

## Estrutura de Arquivos

Os fixtures são salvos em:
```
gris/
  fixtures/
    role.json
    role_profile.json
    carteira.json
    etc...
```

## Comandos Úteis

### Exportar tudo
```bash
bench --site dev.gris export-fixtures
```

### Importar fixtures (durante instalação/migração)
```bash
bench --site dev.gris migrate
```

### Ver quais fixtures estão configuradas
```bash
grep -A 50 "fixtures =" /workspace/frappe-bench/apps/gris/gris/hooks.py
```

## Exemplo Prático: Adicionar Custom Fields

Se você criou Custom Fields no User doctype e quer versioná-los:

1. Adicione no `hooks.py`:
```python
fixtures = [
    # ... outras fixtures ...
    {
        "dt": "Custom Field",
        "filters": [
            ["dt", "=", "User"],
            ["fieldname", "in", ["custom_campo1", "custom_campo2"]]
        ]
    }
]
```

2. Execute:
```bash
bench --site dev.gris export-fixtures
```

3. Commit os arquivos JSON gerados em `gris/fixtures/`

## Dicas

- ✅ Sempre exporte fixtures depois de criar/modificar configurações importantes
- ✅ Commit os arquivos JSON gerados no git
- ✅ Use filtros para exportar apenas o necessário (evita poluir o repositório)
- ✅ Teste a importação em um site limpo para garantir que funciona
- ⚠️ Não versione dados sensíveis (senhas, tokens, etc.)
- ⚠️ Não versione dados transacionais (vendas, compras, etc.) - apenas configuração

## Troubleshooting

### Erro "Fixture not found"
Verifique se o doctype existe e se você tem permissão para acessá-lo.

### Fixtures não importam automaticamente
Execute `bench --site dev.gris migrate` ou `bench --site dev.gris install-app gris`

### Conflitos de fixtures
Se houver conflitos, o Frappe geralmente sobrescreve com os dados do fixture.
