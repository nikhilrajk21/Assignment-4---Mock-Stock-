# Design pipeline

Planned local request and response flow:

```text
Learner
  | enters input or selects an action
  v
Vue UI (frontend/) -- HTTP request --> FastAPI route (backend/)
                                           |
                                           v
                                      Python logic (backend/)
                                           |
                                           v
Vue UI (frontend/) <-- JSON response -- FastAPI route (backend/)
  |
  v
Learner sees the result
```

The Vue frontend will collect input, submit requests, and present loading, error, and result states. FastAPI routes will validate inputs and turn Python results into HTTP responses. Python application logic will handle the financial or market learning operation. Data sources and storage are undecided.

Today the backend and frontend directories are placeholders. No Vue components, routes, Python logic, or storage exist. The README covers setup, AGENTS.md covers working rules, verification.md records checks, and the prompts and handoffs directories preserve assignment and session context.
