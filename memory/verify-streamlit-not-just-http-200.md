---
name: verify-streamlit-not-just-http-200
description: "Verifying a Streamlit app requires confirming the script executed, not just HTTP 200"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: e80f40ac-f90a-4270-8df9-75af5b2a0958
---

I broke the app by changing the entry file (`app/main.py`) to use a relative import (`from .components import ...`). Streamlit runs the entry file as `__main__` (a script, not a package module), so relative imports fail with "attempted relative import with no known parent package". The **entry file must use absolute imports** (`from powerbi_ai_assistant.app.components import ...`); modules it imports can use relative imports normally.

**Why this matters:** I initially declared it "verified" after seeing `HTTP 200`. But 200 only means the Streamlit *server* started — the per-request script execution failed separately, logged as "Uncaught app execution" in the task output. My check missed the actual failure, and the user hit the broken page.

**How to apply:** Never verify a Streamlit (or any server-rendered) app by HTTP status alone. Confirm the script actually executes without error by either (a) running it deterministically as `__main__` — `runpy.run_path("app/main.py", run_name="__main__")` reproduces Streamlit's execution and surfaces ImportErrors (the bare-mode "missing ScriptRunContext" warnings are harmless), or (b) grepping the server log for "Uncaught app execution"/Traceback after triggering a session. Generalize: a process being *up* is not the same as the work *succeeding* — verify the actual behavior. Ties to [[working-style-confirm-and-honest]] (evidence-based, no oversell). Part of [[powerbi-ai-assistant-project]].
