# Gris - Como Rodar o Projeto no Windows

Guia passo a passo para colocar o ambiente **Gris** (Frappe v15) rodando
localmente em uma máquina **Windows**.

> O Frappe depende de ferramentas e scripts shell que não funcionam de
> forma nativa no Windows puro. Por isso, em ambos os caminhos abaixo você
> vai usar o **WSL2** (Linux dentro do Windows) como base. Não é possível
> rodar 100% nativo no Windows sem o WSL2.

## Qual caminho escolher?

| | Docker Compose (manual) | **Frappe Manager (fm)** — recomendado para dev |
|---|---|---|
| Live reload (código Python/JS/CSS) | Não, por padrão | **Sim**, automático no ambiente `dev` |
| Setup | Mais manual (build de imagem, `.env`, criar site) | 1-2 comandos criam tudo |
| Ferramentas extras | — | Mailpit (e-mail), Adminer (DB), debug no VS Code |
| Uso recomendado | Subir o stack completo (Evolution API, Outline, Caddy) tal como em produção | Desenvolver a app `gris` no dia a dia |
| Ainda usa Docker? | Sim | Sim (o `fm` é um wrapper sobre Docker Compose) |

Se você quer **desenvolver** a app com recarregamento automático, vá direto
para a [Opção B — Frappe Manager](#opção-b--frappe-manager-fm-recomendado-para-desenvolvimento).
Se você quer reproduzir o stack completo de produção localmente, use a
[Opção A — Docker Compose](#opção-a--docker-compose-manual).

---

## Pré-requisitos comuns

| Requisito | Observação |
|---|---|
| Windows 10 64-bit (build 19041+) ou Windows 11 | Necessário para WSL2 |
| Virtualização habilitada na BIOS/UEFI | VT-x (Intel) ou AMD-V (AMD) |
| 8 GB de RAM (mínimo) | 4 GB livres para os containers |
| 20 GB de disco livre | Imagens + volumes |

### 1. Instalar o WSL2

Abra o **PowerShell como Administrador**:

```powershell
wsl --install
```

Reinicie o computador quando solicitado e confirme a versão:

```powershell
wsl -l -v
```

A coluna `VERSION` deve mostrar `2`.

### 2. Instalar o Docker Desktop

1. Baixe e instale o [Docker Desktop para Windows](https://www.docker.com/products/docker-desktop/).
2. Mantenha marcada a opção **"Use WSL 2 instead of Hyper-V"** durante a instalação.
3. Em **Settings → Resources → WSL Integration**, habilite a integração com sua distribuição (Ubuntu).

### 3. Instalar o Git para Windows

Baixe em [git-scm.com](https://git-scm.com/download/win) e configure os
finais de linha (o projeto tem scripts `.sh` usados nos containers):

```bash
git config --global core.autocrlf input
```

### 4. Clonar o repositório (dentro do WSL)

Trabalhe **dentro do sistema de arquivos do WSL** (não em `/mnt/c/...`) —
isso é importante tanto para performance quanto para o `fm` funcionar bem.

```bash
wsl
cd ~
git clone https://github.com/inah147/gris.git
cd gris
```

---

## Opção A — Docker Compose (manual)

Use esse caminho se quiser reproduzir o stack completo (igual produção),
sem live reload.

### Passo 1 — Configurar variáveis de ambiente

```bash
cp .env.example .env
```

Ajuste no mínimo:

```dotenv
DB_PASSWORD=uma-senha-forte
FRAPPE_SITE_NAME_HEADER=gris.local
```

> As variáveis de Evolution API e Outline só importam se você for usar
> esses serviços opcionais; os valores padrão (`changeit`) bastam para o
> `docker compose` subir sem erro.

### Passo 2 — Build da imagem Docker

```bash
export APPS_JSON_BASE64=$(base64 -w 0 apps.json)

docker build \
  --build-arg=FRAPPE_PATH=https://github.com/frappe/frappe \
  --build-arg=FRAPPE_BRANCH=version-15 \
  --build-arg=PYTHON_VERSION=3.11.10 \
  --build-arg=NODE_VERSION=18.20.4 \
  --build-arg=APPS_JSON_BASE64=$APPS_JSON_BASE64 \
  --tag=gris:latest \
  --file=Containerfile .
```

### Passo 3 — Subir os containers

```bash
docker compose up -d
docker compose logs configurator -f   # aguarde finalizar, depois Ctrl+C
```

### Passo 4 — Criar o site

```bash
docker compose exec backend bench new-site gris.local \
  --mariadb-user-host-login-scope='%' \
  --db-root-password=uma-senha-forte \
  --admin-password=admin \
  --install-app gris
```

### Passo 5 — Acessar a aplicação

Abra **http://localhost:8080**. Login: `Administrator` / `admin`.

Se usou `FRAPPE_SITE_NAME_HEADER=gris.local`, adicione ao arquivo de hosts
do Windows (Notepad como Administrador,
`C:\Windows\System32\drivers\etc\hosts`):

```
127.0.0.1 gris.local
```

E acesse **http://gris.local:8080**.

### Comandos úteis (Opção A)

```bash
# Migrações após atualizar código
docker compose exec backend bench --site gris.local migrate

# Logs
docker compose logs backend -f
docker compose logs scheduler -f

# Shell do container
docker compose exec backend bash

# Parar / reiniciar
docker compose down
docker compose restart
```

---

## Opção B — Frappe Manager (fm) (recomendado para desenvolvimento)

O [Frappe Manager](https://github.com/rtCamp/Frappe-Manager) (`fm`) é um
CLI que também usa Docker Compose por baixo dos panos, mas automatiza
todo o setup: cria o bench, o site e instala a app com um único comando,
já no modo de desenvolvimento com **live reload** (alterações em
Python/JS/CSS são aplicadas automaticamente), além de incluir Mailpit
(teste de e-mails), Adminer (gerenciador de banco) e integração com
debugger do VS Code.

### Pré-requisitos específicos

- WSL2 + Docker Desktop (Passos 1 a 4 acima)
- Python 3.13+ dentro do WSL (o `fm` é instalado com `uv` ou `pipx`)
- (Opcional) VS Code com a extensão **Dev Containers**, para usar `fm code`

### Passo 1 — Instalar o fm (dentro do WSL)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # se ainda não tiver o uv
uv tool install --python 3.13 frappe-manager
```

Alternativa com `pipx`:

```bash
pipx install frappe-manager
```

### Passo 2 — Criar o bench já com a app gris

A partir da raiz clonada do repositório (ou de qualquer pasta — o `fm`
busca a app diretamente do GitHub):

```bash
fm create gris --apps https://github.com/inah147/gris:main --environment dev
```

Isso cria o bench `gris`, baixa o Frappe e a app `gris`, sobe os
containers e cria o site `gris.localhost`. Se a app não for instalada
automaticamente no site, instale manualmente:

```bash
fm shell gris -c "bench --site gris.localhost install-app gris"
```

### Passo 3 — Acessar a aplicação

Abra **http://gris.localhost**. Login padrão: `Administrator` / `admin`.

> No **Windows 11**, domínios `*.localhost` costumam resolver
> automaticamente. No **Windows 10**, pode ser necessário adicionar ao
> arquivo de hosts (`C:\Windows\System32\drivers\etc\hosts`, como
> Administrador):
> ```
> 127.0.0.1 gris.localhost
> ```

### Passo 4 — Editar código com live reload

No ambiente `--environment dev`, alterações em arquivos Python, JS e CSS
da app são recarregadas automaticamente — não é necessário reiniciar
containers manualmente.

Para editar o código com o VS Code conectado direto ao container (via
extensão **Dev Containers**):

```bash
fm code gris
```

Isso abre o bench no VS Code já com Python, Ruff, ESLint, Prettier e
debugpy configurados.

### Passo 5 — Debug com VS Code (opcional)

```bash
fm code gris --debugger --force-start
```

Isso grava `.vscode/tasks.json` e `.vscode/launch.json` no workspace do
bench. Para depurar:

1. Coloque um breakpoint no código (ex.: em `gris/api/*.py`).
2. Abra o painel **Run and Debug** (`Ctrl+Shift+D`) e aperte **F5**,
   selecionando a configuração gerada pelo `fm`.
3. O VS Code primeiro roda a task `fm-kill-port` (`fmx stop frappe`), que
   para o Gunicorn para liberar a porta para o `debugpy`, e então anexa o
   debugger.
4. Dispare a requisição/ação que aciona o código (ex.: acesse a tela ou
   chame o endpoint no navegador/Postman) — a execução vai parar no
   breakpoint.
5. Ao parar o debug, o Gunicorn volta a subir automaticamente.

### Passo 6 — Popular o site com dados de exemplo (seed)

As fixtures de configuração (roles, centros de custo,
categorias de transação, UOs) já são instaladas automaticamente junto
com a app. Para ter registros de exemplo para testar a interface —
associados, responsáveis e vínculos, leads de novos associados (fila
de espera, agenda de visitas), contas fixas e pagamentos, extrato
financeiro, projetos e entrevistas por competências — use o script
`gris/scripts/seed_demo_data.py`:

```bash
fm shell gris -c "bench --site gris.localhost execute gris.scripts.seed_demo_data.run"
```

O script é idempotente (pode rodar de novo sem duplicar dados) e só
funciona com `developer_mode` ativo, para evitar execução acidental em
produção.

### Ferramentas administrativas

| Ferramenta | URL | Credenciais |
|---|---|---|
| Mailpit (e-mails de teste) | `http://gris.localhost/mailpit/` | `fm info gris` |
| Adminer (gerenciador de banco) | `http://gris.localhost/adminer/` | `fm info gris` |

### Comandos úteis (Opção B)

```bash
fm list              # lista todos os benches
fm info gris         # detalhes e credenciais do bench
fm logs gris -f      # logs em tempo real
fm start gris        # iniciar
fm stop gris         # parar
fm restart gris      # reiniciar serviços
fm shell gris        # shell dentro do bench
fm delete gris       # remove o bench (e opcionalmente o banco)
```

---

## Solução de Problemas (específico do Windows)

| Problema | Causa provável | Solução |
|---|---|---|
| Docker Desktop não inicia / erro de virtualização | Virtualização desabilitada na BIOS, ou Hyper-V/WSL não habilitado | Habilite VT-x/AMD-V na BIOS; habilite "Plataforma de Máquina Virtual" e "Subsistema do Windows para Linux" em Recursos do Windows |
| Tudo muito lento (build, `fm create`, `docker compose up`) | Repositório/bench dentro de `/mnt/c/...` em vez do filesystem do WSL | Trabalhe em `~/` dentro do WSL, nunca em `/mnt/c/...` |
| Erro `$'\r': command not found` ou `nginx-entrypoint.sh: not found` (Opção A) | Scripts `.sh` salvos com final de linha CRLF | `git config --global core.autocrlf input` e re-clone, ou `dos2unix resources/*.sh` |
| Porta 8080 já em uso (Opção A) | Outro serviço usando a porta | Altere `HTTP_PUBLISH_PORT` no `.env` ou pare o serviço conflitante |
| `http://gris.localhost` não abre (Opção B) | Windows 10 não resolve `*.localhost` automaticamente | Adicione `127.0.0.1 gris.localhost` ao arquivo de hosts |
| `configurator` reinicia em loop (Opção A) | Banco de dados ainda não está saudável | `docker compose logs db` para investigar |
| `docker` não é reconhecido no terminal WSL | Integração do Docker Desktop com a distro WSL não habilitada | Docker Desktop → Settings → Resources → WSL Integration → habilite sua distro |
| Build/clone falha (apps do Frappe ou gris) | Firewall corporativo/VPN bloqueando GitHub | Verifique conectividade com `github.com`; desative VPN/proxy para testar |

---

## Referências

- [WSL2 - Microsoft Docs](https://learn.microsoft.com/windows/wsl/install)
- [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/)
- [Frappe Manager (fm) - repositório oficial](https://github.com/rtCamp/Frappe-Manager)
- Guia completo de deploy (Linux/produção): [`DOCKER_DEPLOYMENT.md`](./DOCKER_DEPLOYMENT.md)
- Diretrizes do projeto: [`AGENTS.md`](./AGENTS.md)
