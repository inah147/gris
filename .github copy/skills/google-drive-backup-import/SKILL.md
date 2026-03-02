---
name: google-drive-backup-import
description: Importa os dados do último backup armazenado no Google Shared Drive para um site Frappe, incluindo descoberta do snapshot mais recente, download dos artefatos e restauração segura. Use quando for necessário recuperar ambiente a partir do backup mais novo no Drive.
---

# Importar último backup do Google Drive

## Quando usar
Use esta skill para recuperar um site a partir do snapshot mais recente já enviado para o Shared Drive pelo fluxo de backup do Gris.

## Entregáveis esperados
- Plano de restore seguro com validação de configuração e alvo.
- Identificação objetiva do snapshot mais recente.
- Execução de restore com pós-validação (`migrate` + smoke checks).
- Checklist final de segurança e recuperação operacional.

## Princípios mandatórios desta skill
- Tratar restore como operação destrutiva e irreversível no alvo.
- Confirmar explicitamente o `site` de destino antes de restaurar.
- Nunca expor conteúdo sensível de credenciais em logs.
- Priorizar validação antes de execução (`diagnose`, artefatos, permissões).
- Em caso de falha, preservar evidências mínimas para troubleshooting.

## Contexto do projeto
- Integração existente: `gris/api/backup/google_shared_drive.py`
- Configuração: DocType singleton `Configuracoes Backup Google Drive`
- Agendamento diário: `gris/hooks.py` em `scheduler_events["daily"]`

## Pré-requisitos
1. O DocType `Configuracoes Backup Google Drive` está preenchido e com:
   - `enable_backup`
   - `backup_folder_id`
   - `service_account_json`
2. A Service Account tem acesso de leitura à pasta de backup no Shared Drive.
3. O operador sabe o `site` de destino (ex.: `gris.dev`).

## Fluxo recomendado (plan → validate → execute)

### 1) Validar configuração e destino
Use o método de diagnóstico antes da importação:

```python
frappe.call("gris.api.backup.google_shared_drive.diagnose_destination_folder")
```

Se falhar, corrigir configuração antes de continuar.

### 2) Descobrir o snapshot mais recente
No Drive, o snapshot segue o padrão:

`<site>-backup-YYYY-MM-DDTHH-MM-SSZ`

Selecionar o folder mais recente por `createdTime` dentro de `backup_folder_id`.

### 3) Baixar artefatos do snapshot
Baixar os arquivos para uma pasta temporária local (ex.: `/tmp/restore-<site>`).

Arquivos esperados (podem variar conforme configuração):
- `*-database*.sql.gz`
- `*-site_config_backup*.json`
- `*-files*.tar` ou `*.tgz`
- `*-private-files*.tar` ou `*.tgz`

### 4) Restaurar banco
Executar restore do banco com o arquivo `*-database*.sql.gz`:

```bash
bench --site <site> --force restore /tmp/restore-<site>/<arquivo-database.sql.gz>
```

### 5) Restaurar arquivos públicos/privados (se presentes)
Extrair artefatos no site:

```bash
tar -xf /tmp/restore-<site>/<arquivo-files.tar|tgz> -C sites/<site>/public/files
tar -xf /tmp/restore-<site>/<arquivo-private-files.tar|tgz> -C sites/<site>/private/files
```

Criar os diretórios de destino se necessário antes da extração.

### 6) Pós-restore
Executar migração para alinhar schema e metadados:

```bash
bench --site <site> migrate
```

Validar login, páginas críticas e jobs principais.

## Exemplo: listagem do último snapshot (Python + Google Drive API)
Use este padrão para localizar o folder mais recente com prefixo do site:

```python
from google.oauth2 import service_account
from googleapiclient.discovery import build

creds = service_account.Credentials.from_service_account_info(
    service_account_info,
    scopes=["https://www.googleapis.com/auth/drive"],
)
drive = build("drive", "v3", credentials=creds, static_discovery=False)

query = (
    f"'{backup_folder_id}' in parents and trashed = false "
    "and mimeType = 'application/vnd.google-apps.folder'"
)

resp = drive.files().list(
    q=query,
    fields="files(id,name,createdTime)",
    supportsAllDrives=True,
    includeItemsFromAllDrives=True,
    pageSize=1000,
).execute()

snapshots = [f for f in resp.get("files", []) if f["name"].startswith(f"{site}-backup-")]
latest = sorted(snapshots, key=lambda x: x["createdTime"], reverse=True)[0]
print(latest)
```

## Regras de segurança
- Não exibir nem registrar conteúdo de `service_account_json` em logs.
- Não sobrescrever `site_config.json` automaticamente sem revisão humana.
- Tratar restore como operação destrutiva: confirmar o `site` alvo antes de executar.

## Anti-padrões (evitar)
- Restaurar backup sem validar `backup_folder_id` e acesso da Service Account.
- Executar restore no site errado por falta de confirmação explícita.
- Sobrescrever configuração crítica sem revisão humana.
- Ignorar etapa de `migrate` após restore de banco.
- Concluir operação sem validar login e fluxos críticos.

## Troubleshooting
- **Erro 403/404 no Drive**: verificar compartilhamento da pasta para a Service Account e `backup_folder_id`.
- **Snapshot sem arquivos de files**: conferir flags `include_public_files`/`include_private_files` na configuração.
- **Falha no restore de DB**: validar compatibilidade de versão MariaDB/Frappe e integridade do `*.sql.gz`.

## Checklist final
- [ ] Diagnóstico da pasta de destino executado com sucesso.
- [ ] Snapshot mais recente identificado corretamente para o site alvo.
- [ ] Arquivo `*-database*.sql.gz` baixado e validado.
- [ ] Restore executado no site correto.
- [ ] Migração e validações pós-restore concluídas.
- [ ] Nenhuma credencial sensível foi exposta durante a operação.
