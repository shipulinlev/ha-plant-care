# Development environment

The primary environment is the **dev container** (`.devcontainer/`: Python 3.14, venv at `/home/vscode/.venv`, port 8123). HA cannot run natively on Windows (`homeassistant/runner.py` imports `fcntl`), so integration tests and a live HA run only in the container.

## Container
```bash
npx -y @devcontainers/cli up --workspace-folder .   # start (or VS Code "Reopen in Container")

# inside the container
scripts/setup      # venv + dev dependencies (runs on create)
scripts/test       # ruff check, ruff format --check, mypy, pytest; extra args go to pytest
scripts/develop    # live HA at http://localhost:8123, loading custom_components/ directly
```

From the Windows host, run container commands with `docker exec`:
```bash
docker exec -u vscode -w /workspaces/ha-plants <id> scripts/test
# <id>: docker ps --filter label=devcontainer.local_folder --format '{{.ID}}'
```
In Git Bash prefix `MSYS_NO_PATHCONV=1`, or `/workspaces/...` paths get mangled.

## Windows host quirks
- Git Bash on this machine lacks coreutils (`tail`, `uname`): use PowerShell for host commands.
- PowerShell 5.1 strips embedded double quotes from native-command arguments: keep `"` out of `git commit -m` messages and out of `docker exec ... bash -c` scripts (pipe a script to `docker exec -i ... python3 -` instead).
- Without the container, ruff, mypy and the core tests work from a local venv:
  ```bash
  py -3.14 -m venv .venv && source .venv/Scripts/activate && pip install --group dev
  pytest tests/core -q -p no:homeassistant
  ruff check . && ruff format --check . && mypy .
  ```

## hassfest
CI runs hassfest; run it locally after touching `manifest.json`, `strings.json` or translations:
```bash
docker run --rm -v "$PWD:/github/workspace" ghcr.io/home-assistant/hassfest
```

## Live HA
`scripts/develop` reads config from `config/` (git-ignored), seeded on first run from `.devcontainer/configuration.yaml`. That template has no `default_config` (its `go2rtc` dependency needs a binary the container lacks); add other integrations to it explicitly.
