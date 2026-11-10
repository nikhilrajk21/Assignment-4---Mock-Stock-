# Assignment 4: Financial Knowledge and Market Understanding

This local application is for learners who want to build financial knowledge and better understand markets. The initial goal is to help learners explore financial concepts and relate them to how markets work. The first user workflow and any data sources will be decided before implementation.

## Stack and prerequisites

The planned backend is Python, with FastAPI providing HTTP routes and Uvicorn serving them locally. The planned frontend is Vue, running on Node.js with npm as the proposed package manager. The intended dependency versions and commands will be recorded when the application is scaffolded.

This computer has Windows, Python 3.12.6 (the active interpreter), pip 24.2, FastAPI 0.104.1, Uvicorn 0.24.0, Node.js 24.20.0, npm 11.19.0, pnpm 11.25.0, and Git 2.51.2.windows.1. Vue is not configured in this project. Reuse the active Python environment.

## Running locally

There are no application entry points or run commands yet. From the project root, you can check the current prerequisites in PowerShell:

```powershell
python --version
python -c "import fastapi, uvicorn; print(fastapi.__version__, uvicorn.__version__)"
node --version
npm.cmd --version
```

Add the exact backend and frontend startup commands here once they have been tested.

## Folder map

```text
Assignment 4/
|-- README.md
|-- AGENTS.md
|-- backend/
|-- frontend/
|-- docs/
|   |-- design-pipeline.md
|   `-- verification.md
|-- prompts/
|   `-- 01-generic-project-startup.md
`-- handoffs/
    |-- create-handoff.md
    `-- current.md
```
