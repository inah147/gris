# Gris - Como Rodar o Projeto no Windows

Guia passo a passo para colocar o ambiente **Gris** (Frappe v15) rodando
localmente em uma máquina **Windows**, usando WSL2 + Docker Desktop.

> Esta é a forma recomendada de rodar o projeto no Windows, pois o Frappe
> depende de ferramentas e scripts shell que não funcionam de forma nativa
> no Windows. Todo o ambiente roda em containers Linux via Docker.

---

## Pré-requisitos

| Requisito | Observação |
|---|---|
| Windows 10 64-bit (build 19041+) ou Windows 11 | Necessário para WSL2 |
| Virtualização habilitada na BIOS/UEFI | VT-x (Intel) ou AMD-V (AMD) |
| 8 GB de RAM (mínimo) | 4 GB livres para os containers |
| 20 GB de disco livre | Imagens + volumes |
| Conta de administrador no Windows | Para instalar WSL2 e Docker Desktop |

---

## Passo 1 — Instalar o WSL2

Abra o **PowerShell como Administrador** e execute:

```powershell
wsl --install
```

Isso instala o WSL2 com Ubuntu como distribuição padrão. Reinicie o
computador quando solicitado.

Após reiniciar, confirme que está usando WSL versão 2:

```powershell
wsl -l -v
```

A coluna `VERSION` deve mostrar `2` para a distribuição instalada.

---

## Passo 2 — Instalar o Docker Desktop

1. Baixe e instale o [Docker Desktop para Windows](https://www.docker.com/products/docker-desktop/).
2. Durante a instalação, mantenha marcada a opção **"Use WSL 2 instead of Hyper-V"**.
3. Após instalar, abra o Docker Desktop → **Settings → Resources → WSL Integration**
   e habilite a integração com sua distribuição Ubuntu.
4. Aplique e reinicie o Docker Desktop.

Valide no terminal (PowerShell ou WSL):

```bash
docker --version
docker compose version
```

---

## Passo 3 — Instalar o Git para Windows

Baixe em [git-scm.com](https://git-scm.com/download/win). Durante a
instalação, recomenda-se manter os finais de linha originais (LF), pois o
projeto contém scripts shell (`.sh`) usados dentro dos containers:

```bash
git config --global core.autocrlf input
```

> Se você já clonou o repositório antes de ajustar essa configuração e
> encontrar erros como `nginx-entrypoint.sh: not found` ou
> `$'\r': command not found`, veja a seção de **Solução de Problemas**.

---

## Passo 4 — Clonar o repositório (dentro do WSL)

Para evitar problemas de performance e permissões, trabalhe **dentro do
sistema de arquivos do WSL** (não em `/mnt/c/...`).

Abra um terminal Ubuntu/WSL:

```bash
wsl
cd ~
git clone https://github.com/inah147/gris.git
cd gris
```

---

## Passo 5 — Configurar variáveis de ambiente

```bash
cp .env.example .env
```

Edite o `.env` (pode usar `nano .env` ou abrir a pasta no VS Code com a
extensão *Remote - WSL*) e ajuste no mínimo:

```dotenv
DB_PASSWORD=uma-senha-forte
FRAPPE_SITE_NAME_HEADER=gris.local
```

> As demais variáveis (Evolution API, Outline) só são necessárias se você
> for usar esses serviços opcionais. Para rodar apenas o app Gris
> localmente, os valores padrão (`changeit`) do `.env.example` são
> suficientes para o `docker compose` subir sem erros.

---

## Passo 6 — Build da imagem Docker

Ainda no terminal WSL, na raiz do repositório:

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

Esse build pode levar alguns minutos na primeira vez (baixa o Frappe,
Node.js e dependências Python).

---

## Passo 7 — Subir os containers

```bash
docker compose up -d
```

Acompanhe o serviço `configurator` até ele finalizar (sai do log
automaticamente quando termina):

```bash
docker compose logs configurator -f
```

Pressione `Ctrl+C` para sair do log depois que ele finalizar.

---

## Passo 8 — Criar o site Frappe

```bash
docker compose exec backend bench new-site gris.local \
  --mariadb-user-host-login-scope='%' \
  --db-root-password=uma-senha-forte \
  --admin-password=admin \
  --install-app gris
```

> Substitua `uma-senha-forte` pelo mesmo valor definido em `DB_PASSWORD`
> no `.env`.

---

## Passo 9 — Acessar a aplicação

Abra o navegador em **http://localhost:8080**.

Login: `Administrator` / senha: a definida em `--admin-password` (`admin`
no exemplo acima).

> Se você alterou `FRAPPE_SITE_NAME_HEADER` para algo diferente de
> `localhost` (ex.: `gris.local`), adicione uma entrada no arquivo de hosts
> do Windows para resolver esse nome para `127.0.0.1`:
>
> 1. Abra o Notepad **como Administrador**.
> 2. Abra `C:\Windows\System32\drivers\etc\hosts`.
> 3. Adicione a linha: `127.0.0.1 gris.local`
> 4. Salve e acesse **http://gris.local:8080**.

---

## Comandos úteis (rodar no terminal WSL, dentro da pasta do projeto)

```bash
# Rodar migrações após atualizar o código
docker compose exec backend bench --site gris.local migrate

# Ver logs do backend ou do scheduler
docker compose logs backend -f
docker compose logs scheduler -f

# Entrar no shell do container
docker compose exec backend bash

# Parar todos os containers
docker compose down

# Reiniciar todos os containers
docker compose restart
```

---

## Solução de Problemas (específico do Windows)

| Problema | Causa provável | Solução |
|---|---|---|
| Docker Desktop não inicia / erro de virtualização | Virtualização desabilitada na BIOS, ou Hyper-V/WSL não habilitado | Habilite VT-x/AMD-V na BIOS; em "Recursos do Windows" habilite "Plataforma de Máquina Virtual" e "Subsistema do Windows para Linux" |
| `docker compose up` muito lento ou trava | Repositório clonado em `/mnt/c/...` em vez do filesystem do WSL | Clone o repositório em `~/` dentro do WSL (Passo 4) |
| Erro `$'\r': command not found` ou `nginx-entrypoint.sh: not found` ao iniciar o `frontend` | Scripts `.sh` foram salvos com final de linha CRLF (Windows) | Configure `git config --global core.autocrlf input` e re-clone o repositório, ou rode `dos2unix resources/*.sh` |
| Porta 8080 já em uso | Outro serviço (IIS, Skype, outro container) está usando a porta | Altere `HTTP_PUBLISH_PORT` no `.env` ou pare o serviço conflitante |
| `configurator` reinicia em loop | Banco de dados (`db`) ainda não está saudável | `docker compose logs db` para investigar; aguarde o healthcheck do MariaDB |
| `docker` não é reconhecido no terminal WSL | Integração do Docker Desktop com a distro WSL não habilitada | Docker Desktop → Settings → Resources → WSL Integration → habilite sua distro |
| Build falha em `bench init` / clone do Frappe | Firewall corporativo/VPN bloqueando acesso ao GitHub | Verifique a conectividade com `github.com` e desative VPN/proxy temporariamente para testar |

---

## Referências

- [WSL2 - Microsoft Docs](https://learn.microsoft.com/windows/wsl/install)
- [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/)
- Guia completo de deploy (Linux/produção): [`DOCKER_DEPLOYMENT.md`](./DOCKER_DEPLOYMENT.md)
- Diretrizes do projeto: [`AGENTS.md`](./AGENTS.md)
