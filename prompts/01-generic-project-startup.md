# Generic project startup

Begin by interviewing me about the project. Show me the path of the selected
folder, then ask these questions and wait for my answers before creating or
editing files:

1. How would you describe the project in one or two sentences? Who will use
   it, and what should they be able to do?
2. What should the project folder be called? Is the selected folder already
   the project root, or should the project go in a named folder inside it?
3. What else should guide setup? For example, are there existing files to
   incorporate, a Python environment you already use, or naming conventions
   to follow?

Use any answers I have already given. Ask a focused follow-up if an unknown
affects setup. Summarize the project description, exact folder path, and
agreed constraints before proceeding.

Create the folder structure and documentation for a local application with a
Python backend, a Vue frontend, and FastAPI as the transport layer between them.
Use the agreed path as the project root. Reuse the folder if it exists, or
create it if needed. Inspect its contents and Git status before adding files.
Preserve existing work.

Create any missing parts of the following structure. Create prompts/ only if
it does not already exist. Reuse the existing directory and preserve its files.

```text
<agreed-folder-name>/
|-- README.md                     Project purpose, prerequisites, and setup
|-- AGENTS.md                     Standing instructions for the coding agent
|-- backend/                      Python application logic and FastAPI routes
|-- frontend/                     Vue components, user input, and presentation
|-- docs/
|   |-- design-pipeline.md        File responsibilities and how data moves
|   `-- verification.md           Repeatable checks and observed results
|-- prompts/
|   `-- 01-generic-project-startup.md  This startup prompt
`-- handoffs/
    |-- create-handoff.md         Instructions for ending and resuming a session
    `-- current.md                Current project state, written at handoff
```

Write README.md to include the project overview, goals, technology stacks, dependencies, and run instructions.
Use the project description and intended users from the interview. Include
the actual folder map and the prerequisites found on this computer. Add
startup commands as they become available and are tested.

In AGENTS.md, require the agent to work inside the project root, inspect the
relevant files before editing, and show changes for student review before a
commit. Save each major prompt under prompts/ and its observed results in
docs/verification.md. Keep credentials out of source code, prompts, logs, and
Git. Record this procedure for use whenever a tool or package is needed.

CHECK
Inspect the operating system, active Python interpreter, Node.js, package
managers, dependency files, and lockfiles. Verify which tools and packages are
already available. Reuse the existing Python environment. Do not create or
recreate a virtual environment by default.

TAKE ACTION
For each missing dependency needed for the current task, explain its purpose,
compatible version, exact command, installation target, and files it will
change. Obtain student approval before installing software or changing a
dependency manifest or lockfile.

VERIFY
Run the smallest relevant version, import, or build check in the intended
environment. Record the command, expected result, and observed result in
docs/verification.md. Identify any check that still needs to be run.

In AGENTS.md, define SmokeTest as a repeatable check that runs without source
edits. Once a feature has a UI, the test must start the local services, open a
browser, perform a user operation, and compare its visible result with the
expected result. Check stored data when relevant. Document one command to run
the test and record failures as well as passes. Define AutoLoop as inspecting
a failed check, making the smallest in-scope correction, and rerunning it.
Stop on success, after five correction cycles, or when further permission is needed.

In docs/design-pipeline.md, sketch the planned data flow in ASCII and identify
which parts exist today. Save this prompt in prompts/ only if a copy is missing.
Keep the existing prompt numbering when adding new prompts.
In handoffs/create-handoff.md, include one instruction
for recording the current state and one for verifying it when work resumes.
At the end of setup, use those instructions to write handoffs/current.md with
the files created, checks performed, outstanding questions, and next task.

Finish by displaying the actual folder tree for review.
