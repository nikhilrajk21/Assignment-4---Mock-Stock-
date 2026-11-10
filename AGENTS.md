# Standing project instructions

Work inside this project root. Inspect the relevant files and Git status before editing. Preserve existing work. Show the diff or, when Git is unavailable, the actual changes for student review before committing. Save each major prompt in `prompts/` using the existing numbering sequence, and record its observed results in `docs/verification.md`. Keep credentials out of source code, prompts, logs, and Git.

## When a tool or package is needed

1. **CHECK:** Inspect the operating system, active Python interpreter, Node.js, package managers, dependency files, and lockfiles. Verify what is already available in the intended environment. Reuse the existing Python environment; do not create or recreate a virtual environment by default.
2. **TAKE ACTION:** For each missing dependency needed now, explain its purpose, compatible version, exact command, installation target, and files it will change. Obtain student approval before installing software or changing a dependency manifest or lockfile.
3. **VERIFY:** Run the smallest relevant version, import, or build check in the intended environment. Record the command, expected result, and observed result in `docs/verification.md`. List any check that still needs to run.

## SmokeTest and AutoLoop

**SmokeTest** is a repeatable check that runs without source edits. Once a feature has a UI, the check must start the local services, open a browser, perform a user operation, and compare the visible result with the expected result. Check stored data when relevant. Document one command to run the test and record failures as well as passes. Until a runnable feature exists, mark the browser SmokeTest as pending.

**AutoLoop** means inspecting a failed check, making the smallest in-scope correction, and rerunning it. Stop on success, after five correction cycles, or when further permission is needed.
