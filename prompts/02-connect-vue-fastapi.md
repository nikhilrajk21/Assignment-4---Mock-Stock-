# Connect Vue to FastAPI

Read README.md and AGENTS.md. Inspect backend/, frontend/, manifests and lockfiles. Identify Python, FastAPI, the ASGI server, Node.js, and the package manager. Reuse the Python environment without creating a virtual environment by default.

Show the compatible version, exact command, target, and affected files for missing dependencies. Wait for approval before installing software or editing manifests or lockfiles. Use a minimal Vue setup. Expose GET /api/health in FastAPI and forward /api through the frontend development server.

Start both servers on localhost. Compare direct and proxied health responses. Stop the backend and repeat the proxied request, then restart the backend and check recovery. Record URLs, HTTP status codes, and bodies. Add tested start and stop commands to README.md.

Follow-up: run the frontend also.
