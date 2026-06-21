### Gris

App base para gestão complementar de Grupos Escoteiros

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app gris
```

Para rodar via Docker, veja [`DOCKER_DEPLOYMENT.md`](./DOCKER_DEPLOYMENT.md).

### Rodando no Windows

Se você está usando uma máquina Windows, siga o guia passo a passo em
[`WINDOWS_SETUP.md`](./WINDOWS_SETUP.md). Ele cobre tanto o setup via
Docker Compose quanto via [Frappe Manager](https://github.com/rtCamp/Frappe-Manager)
(recomendado para desenvolvimento, com live reload).

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/gris
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### CI

This app can use GitHub Actions for CI. The following workflows are configured:

- CI: Installs this app and runs unit tests on every push to `develop` branch.
- Linters: Runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.


### License

mit
