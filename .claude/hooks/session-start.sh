#!/bin/bash
# Prepara uma sessão do Claude Code na web para rodar os testes do app.
#
# O container da sessão web sobe só com o repositório clonado: não tem MariaDB,
# não tem bench e o `frappe` não existe no PyPI (o bench clona do GitHub). Sem
# isso, `bench run-tests` não existe e `import frappe` falha — então qualquer
# teste que toque em DocType, permissão ou banco fica sem como rodar.
#
# Este hook monta um bench mínimo, só de backend, apontando para o próprio
# repositório via symlink. Depois de rodar uma vez, o estado do container fica
# em cache e as sessões seguintes reaproveitam.
#
# Como rodar os testes depois que o hook termina:
#   gris-test                   suíte inteira do app (~18s)
#   gris-test contribuicao      só o sistema de contribuição mensal (~4s)
#   gris-test test_extrato_listagem     um módulo avulso
#   bench-gris run-tests --app gris     a forma longa, se precisar de outras flags
#
# Lint, antes de commitar (roda o mesmo que o job "Frappe Linter" do CI):
#   gris-lint
#
# Checagem rápida durante a edição (não substitui o gris-lint):
#   ruff check gris/ && ruff format --check gris/
set -euo pipefail

# Só faz sentido no ambiente remoto; na máquina local o bench é o do Frappe Manager.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

REPO="${CLAUDE_PROJECT_DIR:-/home/user/gris}"
BENCH=/home/frappe/bench
SITE=test.localhost
SEMGREP_RULES=/opt/frappe-semgrep-rules
CA=/etc/ssl/certs/ccr-ca-bundle.crt
export DEBIAN_FRONTEND=noninteractive

log() { echo "[session-start] $*"; }

# ── 1. Pacotes de sistema ───────────────────────────────────────────────────
# `cron` entra porque o `bench init` escreve no crontab e aborta sem o binário.
if ! command -v mariadbd >/dev/null 2>&1 || ! command -v crontab >/dev/null 2>&1; then
  log "instalando mariadb, cron e dependências de build"
  apt-get update -qq >/dev/null 2>&1 || true
  apt-get install -y -qq mariadb-server mariadb-client libmariadb-dev cron \
      build-essential python3.11-venv python3.11-dev pkg-config \
      libssl-dev libffi-dev >/dev/null
fi

# ── 2. MariaDB com o charset que o Frappe exige ─────────────────────────────
if [ ! -f /etc/mysql/mariadb.conf.d/99-frappe.cnf ]; then
  cat > /etc/mysql/mariadb.conf.d/99-frappe.cnf <<'CNF'
[mysqld]
character-set-client-handshake = FALSE
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci
skip-name-resolve
innodb-file-per-table = 1
[mysql]
default-character-set = utf8mb4
CNF
fi

# ── 3. Subir MariaDB e os três Redis que o Frappe espera ────────────────────
mkdir -p /run/mysqld && chown mysql:mysql /run/mysqld
if ! mysqladmin ping >/dev/null 2>&1 && ! mysqladmin -uroot -proot ping >/dev/null 2>&1; then
  log "subindo mariadb"
  (mariadbd --user=mysql >/tmp/mariadb.log 2>&1 &)
  for _ in $(seq 1 60); do
    mysqladmin ping >/dev/null 2>&1 && break
    mysqladmin -uroot -proot ping >/dev/null 2>&1 && break
    sleep 1
  done
fi
for port in 11000 12000 13000; do
  redis-cli -p "$port" ping >/dev/null 2>&1 || redis-server --port "$port" --daemonize yes
done

# ── 4. Usuário root do banco ────────────────────────────────────────────────
# O Frappe conecta por TCP em 127.0.0.1 e, com skip-name-resolve, o MariaDB
# trata isso como host diferente de 'localhost' — daí os dois grants.
if ! mysql -uroot -proot -h127.0.0.1 -e "SELECT 1" >/dev/null 2>&1; then
  log "configurando o root do banco"
  mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED VIA mysql_native_password USING PASSWORD('root'); FLUSH PRIVILEGES;" 2>/dev/null || true
  mysql -uroot -proot -e "
    CREATE USER IF NOT EXISTS 'root'@'127.0.0.1' IDENTIFIED VIA mysql_native_password USING PASSWORD('root');
    GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' WITH GRANT OPTION;
    FLUSH PRIVILEGES;"
fi

# ── 5. Usuário não-root (o bench recusa rodar como root) ────────────────────
id frappe >/dev/null 2>&1 || useradd -m -s /bin/bash frappe

# A CA do proxy vive em /root/.ccr/, ilegível fora do root; sem copiá-la e sem
# exportar as variáveis para o login shell, o pip do usuário `frappe` quebra
# com CERTIFICATE_VERIFY_FAILED.
if [ -f /root/.ccr/ca-bundle.crt ] && [ ! -f "$CA" ]; then
  install -m 0644 /root/.ccr/ca-bundle.crt "$CA"
fi
if [ -f "$CA" ]; then
  cat > /etc/profile.d/00-ccr-proxy.sh <<CERTEOF
export HTTPS_PROXY=${HTTPS_PROXY:-http://127.0.0.1:38999}
export https_proxy=\$HTTPS_PROXY
export NO_PROXY="localhost,127.0.0.1,::1,pypi.org,files.pythonhosted.org,registry.npmjs.org"
export no_proxy="\$NO_PROXY"
export SSL_CERT_FILE=$CA
export REQUESTS_CA_BUNDLE=$CA
export PIP_CERT=$CA
export CURL_CA_BUNDLE=$CA
export GIT_SSL_CAINFO=$CA
export NODE_EXTRA_CA_CERTS=$CA
CERTEOF
  chmod 0644 /etc/profile.d/00-ccr-proxy.sh
fi
echo 'export PATH=/home/frappe/venv/bin:$PATH' > /etc/profile.d/01-frappe-venv.sh
chmod 0644 /etc/profile.d/01-frappe-venv.sh

# ── 6. Bench sem frontend ───────────────────────────────────────────────────
# O `yarn install` do Frappe busca um tarball em codeload.github.com, bloqueado
# pela política de egresso do ambiente. Teste de backend não usa asset nenhum,
# então o passo é neutralizado — este bench serve para testar, não para servir a UI.
mkdir -p /opt/nofrontend
cat > /opt/nofrontend/yarn <<'SHIMEOF'
#!/bin/sh
echo "[shim] yarn ignorado — bench de backend, sem assets de frontend"
exit 0
SHIMEOF
chmod +x /opt/nofrontend/yarn

if [ ! -x /home/frappe/venv/bin/bench ]; then
  log "instalando frappe-bench"
  su - frappe -c "python3.11 -m venv /home/frappe/venv && /home/frappe/venv/bin/pip -q install frappe-bench"
fi

if [ ! -d "$BENCH/apps/frappe" ]; then
  log "bench init (Frappe v15) — passo demorado, só acontece uma vez"
  rm -rf "$BENCH"
  su - frappe -c "export PATH=/opt/nofrontend:\$PATH; cd /home/frappe && bench init --frappe-branch version-15 --python python3.11 --skip-redis-config-generation --skip-assets bench"
  su - frappe -c "cd $BENCH && bench set-config -g redis_cache 'redis://127.0.0.1:13000' \
      && bench set-config -g redis_queue 'redis://127.0.0.1:11000' \
      && bench set-config -g redis_socketio 'redis://127.0.0.1:12000'"
fi

# ── 6b. Manifesto de assets vazio ───────────────────────────────────────────
# `bench run-tests --app gris` cria usuários de teste, e o Frappe monta o e-mail
# de boas-vindas de cada um. Montar esse e-mail passa por `bundled_asset()`, que
# lê `sites/assets/assets.json` — arquivo que o `bench build` geraria e que este
# bench, sem frontend, nunca gera. Sem ele a leitura devolve None e a suíte
# inteira morre no bootstrap com `AttributeError: 'NoneType' object has no
# attribute 'get'`, antes do primeiro teste.
#
# Um objeto vazio basta: nenhum teste de backend resolve caminho de asset, e o
# `bundled_asset` cai no fallback de devolver o caminho original.
mkdir -p "$BENCH/sites/assets"
[ -f "$BENCH/sites/assets/assets.json" ] || printf '{}' > "$BENCH/sites/assets/assets.json"
chown -R frappe:frappe "$BENCH/sites/assets"

# ── 7. O app é um symlink para o repositório: editou, vale na hora ──────────
chmod o+rx /home/user "$REPO" 2>/dev/null || true
if [ ! -L "$BENCH/apps/gris" ]; then
  rm -rf "$BENCH/apps/gris"
  ln -s "$REPO" "$BENCH/apps/gris"
fi
printf 'frappe\ngris\n' > "$BENCH/sites/apps.txt"
chown frappe:frappe "$BENCH/sites/apps.txt"
su - frappe -c "cd $BENCH && ./env/bin/pip -q install -e apps/gris" >/dev/null

# ── 8. Site ─────────────────────────────────────────────────────────────────
if [ ! -f "$BENCH/sites/$SITE/site_config.json" ]; then
  log "criando o site $SITE"
  rm -rf "${BENCH:?}/sites/$SITE"
  su - frappe -c "cd $BENCH && bench new-site $SITE --db-root-password root --admin-password admin --mariadb-user-host-login-scope='%'"
  su - frappe -c "export PATH=/opt/nofrontend:\$PATH; cd $BENCH && bench --site $SITE install-app gris"
  su - frappe -c "cd $BENCH && bench --site $SITE set-config allow_tests true"
else
  # Site já existe (container em cache): alinhar o schema com o código atual.
  # Alguns DocTypes (ex.: Role Profile) enfileiram jobs no on_update. Este bench
  # não roda workers, então o job nunca é consumido e o lock trava o próximo
  # migrate com DocumentLockedError — daí a limpeza antes.
  rm -f "$BENCH/sites/$SITE/locks/"*.lock 2>/dev/null || true
  log "aplicando migrações pendentes"
  su - frappe -c "export PATH=/opt/nofrontend:\$PATH; cd $BENCH && bench --site $SITE migrate" >/dev/null 2>&1 || \
    log "aviso: migrate falhou; rode 'bench-gris migrate' para ver o erro"
fi

# Nunca deixar o scheduler acordar: os jobs diários deste app mandam WhatsApp
# para famílias reais, sincronizam Google Workspace e sobem backup para o Drive.
su - frappe -c "cd $BENCH && bench --site $SITE set-config pause_scheduler 1 && bench --site $SITE set-config mute_emails 1" >/dev/null 2>&1 || true

# ── 9. Linters ──────────────────────────────────────────────────────────────
# O job "Frappe Linter" do CI roda duas coisas, nesta ordem:
#   1. pre-commit run --all-files
#   2. semgrep ci --config ./frappe-semgrep-rules/rules --config r/python.lang.correctness
#      (o segundo --config vem de semgrep.dev, inalcançável daqui — ver o gris-lint)
#
# As duas precisam existir aqui, senão o erro só aparece depois de abrir o PR.
# E não basta ter as ferramentas: o pre-commit fixa as versões em
# .pre-commit-config.yaml (prettier 2.7.1, eslint 8.44, ruff 0.16.4) e formatar
# com outra versão reprova o CI — por isso o `gris-lint` chama o pre-commit em
# vez dos binários soltos.

# ruff e eslint soltos: úteis para uma checagem rápida durante a edição.
command -v ruff >/dev/null 2>&1 || pip install -q ruff >/dev/null 2>&1 || true

# O repositório usa `.eslintrc` (formato legado). A imagem traz o ESLint 10, que
# só aceita flat config e aborta antes de lintar qualquer coisa — por isso a
# checagem é de versão, não de existência. A v8 é a última que lê este formato.
eslint_major="$(eslint --version 2>/dev/null | sed 's/^v//; s/\..*//')"
if [ -z "$eslint_major" ] || [ "$eslint_major" -ge 9 ] 2>/dev/null; then
  log "instalando eslint 8 (a v${eslint_major:-?} não lê o .eslintrc deste repo)"
  npm install -g --silent eslint@8 >/dev/null 2>&1 || log "aviso: eslint não instalado"
fi

command -v pre-commit >/dev/null 2>&1 || {
  log "instalando pre-commit"
  pip install -q pre-commit >/dev/null 2>&1 || log "aviso: pre-commit não instalado"
}

# Baixa os ambientes dos hooks agora: eles entram no cache do container, então o
# primeiro `gris-lint` da sessão não gasta um minuto montando node/venv.
if command -v pre-commit >/dev/null 2>&1 && [ ! -d "$HOME/.cache/pre-commit" ]; then
  log "preparando os ambientes do pre-commit (uma vez só)"
  (cd "$REPO" && pre-commit install-hooks) >/dev/null 2>&1 || \
    log "aviso: falha ao preparar os hooks; o gris-lint vai montá-los na primeira execução"
fi

# --ignore-installed PyJWT: a imagem traz o PyJWT do apt, sem RECORD, e o pip
# aborta a instalação inteira ao tentar desinstalá-lo.
if ! command -v semgrep >/dev/null 2>&1; then
  log "instalando semgrep"
  pip install -q --ignore-installed PyJWT semgrep >/dev/null 2>&1 || log "aviso: semgrep não instalado"
fi

if [ ! -d "$SEMGREP_RULES/rules" ]; then
  log "baixando as regras de semgrep do Frappe"
  rm -rf "$SEMGREP_RULES"
  git clone --depth 1 -q https://github.com/frappe/semgrep-rules.git "$SEMGREP_RULES" 2>/dev/null || \
    log "aviso: regras de semgrep não baixadas; o gris-lint vai avisar"
fi

# ── 10. Atalhos ─────────────────────────────────────────────────────────────
cat > /usr/local/bin/bench-gris <<BENCHEOF
#!/bin/sh
# Roda um comando do bench contra o site de testes, como o usuário frappe.
exec su - frappe -c "export PATH=/opt/nofrontend:\\\$PATH; cd $BENCH && bench --site $SITE \$*"
BENCHEOF
chmod +x /usr/local/bin/bench-gris

cat > /usr/local/bin/gris-test <<'TESTEOF'
#!/bin/bash
# Atalho para os testes, com os nomes de módulo que mais se repetem.
#
#   gris-test                 suíte inteira do app (~18s)
#   gris-test contribuicao    só o sistema de contribuição mensal (~4s)
#   gris-test test_extrato_listagem gris.api.financeiro.test_conciliacao
#                             módulos avulsos; nome curto vira gris.tests.<nome>
#
# Vale a pena rodar o conjunto pequeno enquanto se edita e a suíte inteira antes
# de commitar: a diferença é de segundos, e a suíte pega o que o recorte não vê
# (foi um teste de outro módulo que apanhou a última regressão de schema).
set -uo pipefail

# Módulos que cobrem a contribuição mensal ponta a ponta: apuração, cobrança
# InfinitePay, baixa no extrato, séries do painel, tela de detalhe do
# contribuinte e ferramentas MCP.
CONTRIBUICAO="
gris.tests.test_contribuicoes_transacoes
gris.tests.test_cobranca_contribuicao
gris.tests.test_contribuicao_detalhe
gris.tests.test_dashboard_contribuicoes
gris.tests.test_mcp_contribuicoes
"

if [ "$#" -eq 0 ]; then
  exec bench-gris run-tests --app gris
fi

if [ "$1" = "contribuicao" ] || [ "$1" = "contrib" ]; then
  set -- $CONTRIBUICAO
fi

falhou=0
for modulo in "$@"; do
  case "$modulo" in
    *.*) ;;                        # já veio com o caminho completo
    *) modulo="gris.tests.$modulo" ;;
  esac
  echo "== $modulo =="
  bench-gris run-tests --module "$modulo" || falhou=1
done
exit "$falhou"
TESTEOF
chmod +x /usr/local/bin/gris-test

# Heredoc citado de propósito: nada é expandido aqui, então o `$falhou` do
# script chega inteiro. Os dois caminhos entram logo abaixo, via sed.
cat > /usr/local/bin/gris-lint <<'LINTEOF'
#!/bin/bash
# Reproduz o job "Frappe Linter" do CI, na mesma ordem e com as mesmas versões.
# Rode antes de commitar: o que passar aqui passa lá.
#
# O pre-commit corrige o que consegue (formatação) e sai com erro quando mexeu
# em algum arquivo — nesse caso é só conferir o diff e rodar de novo.
set -uo pipefail
cd "@REPO@" || exit 1

falhou=0

echo "== pre-commit: ruff, prettier 2.7.1, eslint 8 (versões fixadas no .pre-commit-config.yaml) =="
if command -v pre-commit >/dev/null 2>&1; then
  pre-commit run --all-files || falhou=1
else
  echo "pre-commit não instalado — rode: pip install pre-commit"
  falhou=1
fi

echo
echo "== semgrep: regras do Frappe (SQL cru, permissões, correção) =="
if ! command -v semgrep >/dev/null 2>&1; then
  echo "semgrep não instalado — rode: pip install --ignore-installed PyJWT semgrep"
  falhou=1
elif [ ! -d "@RULES@/rules" ]; then
  echo "regras ausentes — rode: git clone --depth 1 https://github.com/frappe/semgrep-rules.git @RULES@"
  falhou=1
else
  # --error é obrigatório: sem ele o semgrep lista os findings e mesmo assim sai 0.
  #
  # O CI acrescenta `--config r/python.lang.correctness`, que baixa as regras de
  # semgrep.dev. Aqui esse host é barrado pela política de egresso do ambiente
  # (403 no proxy), então essa parte fica só no CI. As regras do Frappe — as que
  # pegam SQL montado à mão, permissão frouxa e afins — rodam offline daqui.
  semgrep scan --config "@RULES@/rules" --metrics=off --error --quiet . || falhou=1
fi

echo
if [ "$falhou" -eq 0 ]; then
  echo "gris-lint: tudo limpo."
else
  echo "gris-lint: há pendências acima — corrija antes de commitar."
fi
exit "$falhou"
LINTEOF
sed -i "s|@REPO@|$REPO|g; s|@RULES@|$SEMGREP_RULES|g" /usr/local/bin/gris-lint
chmod +x /usr/local/bin/gris-lint

# Caminhos do bench ficam disponíveis para o resto da sessão, para quem precisar
# chamar o bench direto em vez de pelos atalhos.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo "export GRIS_BENCH=$BENCH"
    echo "export GRIS_SITE=$SITE"
  } >> "$CLAUDE_ENV_FILE"
fi

log "pronto — testes: gris-test (tudo) ou gris-test contribuicao | lint: gris-lint"
