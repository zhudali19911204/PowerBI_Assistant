# Project Memory Index

- [PowerBI AI Assistant project](powerbi-ai-assistant-project.md) — what it is: goals, phases, MVP=DAX, Desktop-only, Python/Streamlit/replaceable-LLM, 4-abstraction architecture
- [Live EVALUATE validation is required](live-evaluate-validation-is-required.md) — why run-verifying DAX is a hard phase-1 requirement (models emit self-consistent-but-wrong measures)
- [DAX skill eval workflow](dax-skill-eval-workflow.md) — how to benchmark/improve dax-expert skill + prompts.py with real cases (harness, Windows PYTHONUTF8=1 gotcha)
- [Working style: confirm + honest](working-style-confirm-and-honest.md) — user wants confirmation before building and evidence-based, no-oversell assessments
- [Verify Streamlit, not just HTTP 200](verify-streamlit-not-just-http-200.md) — HTTP 200 = server up, not script ok; entry file needs absolute imports; verify via runpy/__main__ or log grep
- [Corporate TLS inspection needs truststore](corporate-tls-inspection-needs-truststore.md) — ContiTech MITM proxy re-signs HTTPS; Python must use OS trust store (truststore) not certifi, else APIConnectionError
- [pbixray blind to calc-table columns & relationships](pbixray-blind-to-calc-table-columns-and-relationships.md) — static parse can't see calc tables' columns/relationships (only name+DAX); a grounding gap that makes M6 live connection required for grounding, not just validation
- [Live connection works via bundled ADOMD](live-connection-works-via-bundled-adomd.md) — zero-install live AS connection: load Power BI's own Microsoft.PowerBI.AdomdClient.dll via pythonnet, query TMSCHEMA DMVs; proven to close the calc-table gap
