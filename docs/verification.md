# Verification

## 2026-11-10 — Project startup

| Command or inspection | Expected | Observed |
| --- | --- | --- |
| `[Environment]::OSVersion.VersionString` and `$PSVersionTable.PSVersion.ToString()` | Identify host and shell | Windows NT 10.0.26300.0; PowerShell 7.6.9 |
| `Get-ChildItem -Force -LiteralPath $p` with `$p` set to the project root | Inspect all existing entries | Zero entries before setup; no dependency manifests, lockfiles, prompts, or local .git marker |
| `git -C $p status --short --branch` | Report branch/status or say the folder is not in a repository | The sandboxed process could not enter the directory; see target verification below |
| `python -c "import sys; print(sys.version); print(sys.executable); print(sys.prefix != sys.base_prefix)"` (equivalent fields from the startup check) | Identify active interpreter and whether it is in a venv | Python 3.12.6 at `C:\Users\nikhi\AppData\Local\Programs\Python\Python312\python.exe`; venv: False |
| Python package metadata lookup using `importlib.metadata` | Identify installed package versions | pip 24.2; FastAPI 0.104.1; Uvicorn 0.24.0 |
| `python -c "import fastapi, uvicorn; print(fastapi.__version__, uvicorn.__version__)"` | Both imports succeed | Pass: 0.104.1 and 0.24.0 |
| `node --version`, `npm.cmd --version`, `pnpm.cmd --version`, `git --version` | Report available tool versions | Node.js 24.20.0; npm 11.19.0; pnpm 11.25.0; Git 2.51.2.windows.1 |
| `Get-Command python,py,node,npm,npm.cmd,pnpm,yarn,uv,git -ErrorAction SilentlyContinue` | Identify available tools | Python, Python Launcher, Node.js, npm, pnpm, and Git found; Yarn and uv not found on PATH |

No software was installed, no dependency files were changed, and no virtual environment was created. Build, startup, endpoint, and browser SmokeTest checks are pending because the application has no runnable feature yet.

Target Git check (before writing), exit 128:

    fatal: not a git repository (or any of the parent directories): .git
