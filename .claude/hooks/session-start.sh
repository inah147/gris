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
#   bench-gris run-tests --app gris
#   bench-gris run-tests --module gris.tests.test_contribuicoes_transacoes
#
# Lint:
#   ruff check gris/ && ruff format --check gris/
#   eslint gris/www/<rota>.js
set -euo pipefail

# Só faz sentido no ambiente remoto; na máquina local o bench é o do Frappe Manager.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

REPO="${CLAUDE_PROJECT_DIR:-/home/user/gris}"
BENCH=/home/frappe/bench
SITE=test.localhost
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
# ruff normalmente já vem na imagem; garantir não custa nada.
command -v ruff >/dev/null 2>&1 || pip install -q ruff >/dev/null 2>&1 || true

# O repositório usa `.eslintrc` (formato legado). A imagem traz o ESLint 10, que
# só aceita flat config e aborta antes de lintar qualquer coisa — por isso a
# checagem é de versão, não de existência. A v8 é a última que lê este formato.
eslint_major="$(eslint --version 2>/dev/null | sed 's/^v//; s/\..*//')"
if [ -z "$eslint_major" ] || [ "$eslint_major" -ge 9 ] 2>/dev/null; then
  log "instalando eslint 8 (a v${eslint_major:-?} não lê o .eslintrc deste repo)"
  npm install -g --silent eslint@8 >/dev/null 2>&1 || log "aviso: eslint não instalado"
fi

# ── 10. Atalho para rodar comandos do bench ─────────────────────────────────
cat > /usr/local/bin/bench-gris <<BENCHEOF
#!/bin/sh
# Roda um comando do bench contra o site de testes, como o usuário frappe.
exec su - frappe -c "export PATH=/opt/nofrontend:\\\$PATH; cd $BENCH && bench --site $SITE \$*"
BENCHEOF
chmod +x /usr/local/bin/bench-gris

log "pronto — use: bench-gris run-tests --app gris"
