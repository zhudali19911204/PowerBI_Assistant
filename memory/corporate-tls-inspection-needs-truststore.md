---
name: corporate-tls-inspection-needs-truststore
description: "ContiTech network does TLS inspection; Python HTTPS to external APIs needs the OS trust store (truststore), not certifi"
metadata: 
  node_type: memory
  type: project
  originSessionId: e80f40ac-f90a-4270-8df9-75af5b2a0958
---

The user's corporate network (ContiTech) runs a **TLS-inspecting proxy** that re-signs all HTTPS with a private root CA — observed issuer: `CN=sia.ct-ind.com, O=ContiTech Deutschland GmbH, OU=Internet Access Service`. Browsers work because IT installed that root in the **Windows certificate store**, but Python verifies against the bundled **certifi** CA list, which does NOT contain it. Result: every outbound HTTPS API call (LLM providers, web fetch, any external service) fails with `APIConnectionError` / `[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate`. TCP connects fine (host reachable) — only the cert verification fails, which distinguishes it from a real network outage.

**Why:** This is an environment constraint, not a code bug. It will recur for ANY new feature that makes HTTPS calls from Python. It first surfaced when the user tested a Doubao/Volcengine (`ark.cn-beijing.volces.com`) OpenAI-compatible provider and got `APIConnectionError: Connection error.`

**How to apply:** The fix is `truststore` — it makes Python's `ssl` verify against the OS trust store (which has the corporate root), so TLS verification still happens (NOT `verify=False`). It's wired in [powerbi_ai_assistant/net.py](powerbi_ai_assistant/net.py) `enable_os_trust_store()` (idempotent, best-effort) and called inside `llm/factory.build_provider()` before any HTTPS client is created. For future modules that open their own HTTPS connections outside the factory (e.g. a web-fetch ContextSource), call `enable_os_trust_store()` first. To diagnose a "connection error": check `connect=` time in curl (fast connect + TLS failure = MITM proxy, not outage) and decode the cert issuer via stdlib `ssl`. Verify a fix by reaching the endpoint with a fake key and confirming a **401/auth** error (TLS OK) rather than a **connection** error. Ties to [[verify-streamlit-not-just-http-200]] (verify the real behavior, not a proxy signal). Part of [[powerbi-ai-assistant-project]].
