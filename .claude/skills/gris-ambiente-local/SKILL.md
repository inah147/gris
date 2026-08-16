---
name: gris-ambiente-local
description: Sobe, atualiza e valida a aplicação GRIS localmente no Windows via WSL2 + Frappe Manager, incluindo sincronização do código para o bench, quando rodar migrate, restauração de dumps e blindagem contra efeitos colaterais em produção. Use sempre que o pedido for rodar/subir/reiniciar a app local, atualizar o ambiente após um pull ou troca de branch, importar um backup para testes, ou diagnosticar por que o site local não responde.
---

# Ambiente local do GRIS (Windows + WSL2 + Frappe Manager)

## Quando usar
- "rode a aplicação local", "sobe o ambiente", "reinicia o bench";
- "atualiza o local com a branch X" / "peguei as últimas alterações";
- "aplica esse backup para eu ver os dados";
- o site local não abre, devolve 503, 413 ou os containers caíram.

## O que este ambiente é
Não há Docker Desktop utilizável nesta máquina — ele falha ao iniciar com erro de
*Inference manager*. O ambiente roda em **Docker Engine nativo dentro do WSL2
(Ubuntu, com systemd)**, orquestrado pelo **Frappe Manager (`fm`)**.

| Item | Valor |
|---|---|
| Distro | `Ubuntu` (systemd ativo; `docker.service` gerenciado por systemd) |
| Bench | `gris` — site `gris.localhost` |
| Raiz do bench (host WSL) | `/home/lucas/frappe/sites/gris.localhost/workspace/frappe-bench` |
| Mesmo caminho dentro do container | `/workspace/frappe-bench` |
| Container da app | `fm__gris_localhost__frappe` (usuário `frappe`) |
| Proxy global | `fm_global-nginx-proxy` (`jwilder/nginx-proxy:1.6`) |
| Banco | `fm_global-db` (MariaDB, compartilhado entre benches) |

**Nunca** tente iniciar o Docker Desktop. Use sempre `wsl -d Ubuntu`.

## Princípios mandatórios
- O diretório da app no bench é uma **cópia separada** do repositório. Editar
  `C:\GIT\gris` não altera o que roda em `gris.localhost` até sincronizar.
- `migrate` só quando o diff mexer em `gris/patches.txt` ou em DocTypes. Rodar por
  reflexo sobre dados restaurados é risco desnecessário.
- Restore é destrutivo e irreversível no alvo: confirme o site antes.
- Com dados de produção no local, `pause_scheduler` e `mute_emails` são obrigatórios.
- Nunca ler, imprimir ou repetir senhas — aponte onde estão e deixe o operador digitar.

## Fluxo operacional

### 1) Subir o ambiente
```bash
wsl -d Ubuntu -- bash -lc "fm start gris"
```

A distro WSL **desliga por ociosidade e derruba os containers** (saem com exit 0,
shutdown gracioso do systemd). Para segurar durante a sessão, mantenha um processo
vivo em background:

```bash
wsl -d Ubuntu -- bash -lc "sleep 86400"
```

Correção durável: `vmIdleTimeout` em `C:\Users\<user>\.wslconfig` (arquivo global,
afeta todas as distros — confirme com o usuário antes de criar), ou simplesmente
deixar um terminal WSL aberto.

### 2) Sincronizar o código do repositório para o bench
Este é o passo que falta com mais frequência.

```bash
wsl -d Ubuntu -- bash -lc 'rsync -a --delete --exclude=node_modules --exclude=__pycache__ --exclude=.ruff_cache --exclude=backup /mnt/c/GIT/gris/ /home/lucas/frappe/sites/gris.localhost/workspace/frappe-bench/apps/gris/'
```

O `.git` vai junto, então dá para conferir o estado com
`git branch --show-current` dentro do diretório do bench. `--exclude=backup` evita
duplicar dumps com dados pessoais.

### 3) Decidir se precisa de `migrate`
```bash
git diff --stat <ref-anterior>..HEAD -- gris/patches.txt "*/doctype/*"
```

Vazio → pule. Não vazio → rode:

```bash
wsl -d Ubuntu -- bash -lc 'docker exec -u frappe -w /workspace/frappe-bench fm__gris_localhost__frappe bench --site gris.localhost migrate'
```

### 4) Recarregar
```bash
wsl -d Ubuntu -- bash -lc 'docker exec -u frappe -w /workspace/frappe-bench fm__gris_localhost__frappe bench --site gris.localhost clear-cache && fm restart gris'
```

### 5) Validar
```bash
wsl -d Ubuntu -- bash -lc 'curl -sL -o /dev/null -w "%{http_code} %{url_effective}\n" --retry 25 --retry-delay 5 --retry-all-errors -H "Host: gris.localhost" http://127.0.0.1/'
```

Esperado: `200 http://127.0.0.1/login?redirect-to=/inicio`.

Para checar se uma rota existe sem autenticar: `301` = existe (redireciona para
login); `404` = não existe. Sempre compare com uma rota inventada como controle.

## Acesso pelo navegador
**http://gris.localhost** — `Administrator` / `admin`.

`gris.localhost` só resolve **no navegador** (Chrome/Edge resolvem `*.localhost`
internamente). PowerShell, `curl` e `Invoke-WebRequest` no Windows **não resolvem** —
use `-H "Host: gris.localhost" http://127.0.0.1/` de dentro do WSL, ou adicione
`127.0.0.1 gris.localhost` ao arquivo de hosts (requer admin).

Ferramentas: `/mailpit/` e `/adminer/` (credenciais em `fm info gris`).

## Restaurar um dump (dados de produção)

1. **Blindar antes** dos dados entrarem:
```bash
wsl -d Ubuntu -- bash -lc 'docker exec -u frappe -w /workspace/frappe-bench fm__gris_localhost__frappe bench --site gris.localhost set-config pause_scheduler 1'
```
Repita para `mute_emails 1`.

2. Copiar o dump para um caminho visível ao container
   (`.../frappe-bench/sites/`) e restaurar. O comando **pede a senha root do
   MariaDB** — ela está em `fm info gris` ou na chave `MYSQL_ROOT_PASSWORD` de
   `/home/lucas/frappe/services/docker-compose.yml`. Aponte o local e deixe o
   operador executar; não leia o valor.

```bash
docker exec -it -u frappe -w /workspace/frappe-bench fm__gris_localhost__frappe bench --site gris.localhost --force restore sites/<arquivo>.sql.gz
```

`bench restore` aceita `--db-root-password` para rodar sem prompt, mas isso expõe
a senha no histórico do shell e no `ps`.

3. `migrate`, `clear-cache` e trocar a senha do Administrator — o dump traz o hash
   do site de origem, então o `admin` local não funciona até isso:

```bash
wsl -d Ubuntu -- bash -lc 'docker exec -u frappe -w /workspace/frappe-bench fm__gris_localhost__frappe bench --site gris.localhost set-admin-password admin'
```

### Por que restaurar só o banco
`api_key` e `service_account_json` são fieldtype `Password`, criptografados com a
`encryption_key` do `site_config.json` do site de origem. Restaurando **apenas** o
`.sql.gz`, sem o `site_config.json`, essas credenciais falham ao descriptografar em
vez de funcionar — é uma camada de proteção real. Nunca copie o `site_config.json`
de produção.

### Por que o scheduler importa
`gris/hooks.py` agenda diariamente: lembretes por WhatsApp às 09:00 para famílias
reais, sincronização de acessos do Google Workspace, e `enqueue_daily_backup`, que
**sobrescreve o backup de produção no Google Drive**. Com dados reais no local e o
scheduler solto, a máquina do desenvolvedor executa isso para valer.

### Efeito colateral esperado do migrate
DocTypes de apps instalados só em produção (ex.: `DuckDB Sync`, `Security Settings`)
são apagados como órfãos no site local. O banco de produção não é tocado, mas o
local deixa de ser réplica fiel. Avise o operador.

Dumps de banco não trazem anexos — arquivos e fotos aparecem como links quebrados.

## Rodar testes
```bash
wsl -d Ubuntu -- bash -lc 'docker exec -u frappe -w /workspace/frappe-bench fm__gris_localhost__frappe bench --site gris.localhost run-tests --app gris --module <modulo>'
```

Testes criam e apagam registros: **não rode sobre um banco restaurado** que o
usuário quer usar como retrato de produção sem avisar antes.

Se aparecer `frappe.exceptions.ValidationError: Throttled`, é o
`throttle_user_creation` do Frappe (limite de usuários criados por hora, default 60).
Destrave com:

```bash
wsl -d Ubuntu -- bash -lc 'docker exec -u frappe -w /workspace/frappe-bench fm__gris_localhost__frappe bench --site gris.localhost set-config throttle_user_limit 1000 --parse'
```

O `--parse` é obrigatório: sem ele o valor vira string e o Frappe quebra com
`'>' not supported between instances of 'int' and 'str'`.

## Armadilhas do `wsl.exe` (economizam muito tempo)
O `wsl.exe` remonta a linha de comando e o MSYS do Git Bash converte caminhos.
Consequências reais já observadas:

| Sintoma | Causa | Contorno |
|---|---|---|
| Variável de shell vem vazia (`P=/x; ls $P` lista o diretório errado) | argumentos remontados | não use variáveis; escreva caminhos absolutos literais |
| `$HOME` vazio (mas `~` funciona) | ambiente não exportado | use `/home/lucas` explícito |
| `for c in a b; do ...$c...` roda com valor vazio | idem | não use loops; repita o comando |
| `curl --data-binary @/tmp/f` → "error reading file" | MSYS converte `@/tmp/...` | use pipe: `cmd \| curl --data-binary @-` |
| Redirect `> /tmp/f` some | `/tmp` é convertido | use `/home/lucas/...` |
| Backticks em SQL viram substituição de comando | bash | use a API do Frappe (`frappe.db.count` com filtros) |

Para Python complexo, canalize por stdin — pipes não sofrem mangling:

```bash
wsl -d Ubuntu -- bash -lc 'echo "import frappe; print(frappe.db.count(\"Associado\"))" | docker exec -i -u frappe -w /workspace/frappe-bench fm__gris_localhost__frappe bench --site gris.localhost console'
```

## Troubleshooting

| Sintoma | Causa | Correção |
|---|---|---|
| Containers `Exited (0)` sem ninguém parar | distro WSL desligou por ociosidade | `fm start gris` + keep-alive (passo 1) |
| `503` do proxy | bench ainda subindo | aguarde e repita o curl com `--retry` |
| `413 Request Entity Too Large` no upload | `client_max_body_size` do **proxy global** não definido → default 1 MB do nginx (o nginx do bench já permite 50m) | crie `/home/lucas/frappe/services/nginx-proxy/confd/fm_upload_size.conf` com `client_max_body_size 50m;`, então `docker exec fm_global-nginx-proxy nginx -t && docker exec fm_global-nginx-proxy nginx -s reload` |
| Upload falha acima de 10 MB sem ser 413 | teto do Frappe: `frappe/utils/file_manager.py` → `conf.get("max_file_size") or 10485760` | `bench --site gris.localhost set-config max_file_size 52428800 --parse` |
| `fm shell gris -c "..."` → "No such option: -c" | esta versão do `fm` não aceita `-c` | use `docker exec -u frappe -w /workspace/frappe-bench fm__gris_localhost__frappe <cmd>` |
| Código novo não aparece no site | faltou o rsync do passo 2 | rode o passo 2 |

## Anti-padrões
- Tentar iniciar o Docker Desktop.
- Editar arquivos direto no diretório do bench — a próxima sincronização sobrescreve.
- Rodar `migrate` sem verificar se `patches.txt`/DocTypes mudaram.
- Restaurar dump de produção sem `pause_scheduler` e `mute_emails`.
- Copiar o `site_config.json` de produção junto com o dump.
- Ler ou ecoar a senha root do MariaDB para "facilitar".
- Rodar testes sobre um banco restaurado sem avisar que ele será modificado.
- Deixar dumps de produção fora de `backup/` (que é gitignored) ou esquecê-los na máquina.

## Checklist final
- [ ] `fm start gris` executado e containers de pé.
- [ ] Código sincronizado para o bench e branch conferida com `git branch --show-current`.
- [ ] `migrate` decidido por evidência (diff de `patches.txt`/DocTypes), não por hábito.
- [ ] `clear-cache` + `fm restart gris`.
- [ ] Site responde `200` e as rotas relevantes resolvem.
- [ ] Se houver dados de produção: `pause_scheduler` e `mute_emails` confirmados.
- [ ] Nenhuma credencial lida, impressa ou repetida.
