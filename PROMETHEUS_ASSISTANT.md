# PROMETHEUS_ASSISTANT

Goal: make Prometheus metrics *discoverable and usable* for humans without everyone hand-writing brittle PromQL.

Prometheus (example): `https://prometheus.prod.data.platform.smec.services`

---

## 1) Problem statement
- We have a vast amount of metrics and labels; it’s hard to know **what exists**, **what matters**, and **how to query it**.
- PromQL is powerful but brittle:
  - label/metric name drift
  - inconsistent label conventions across teams
  - copy/paste queries that break silently
- We want an “assistant” that helps people go from **intent → validated query → visualization → next steps**.

---

## 2) What “Prometheus Assistant” should do (requirements)

### Core user stories (initial)
- [ ] “Show me CPU usage for ArgoCD in the last 1h” → assistant generates PromQL + opens graph URL + explains labels.
- [ ] “Which services in namespace X are erroring?” → propose 2–3 candidate queries and ask clarifying questions.
- [ ] “What does this alert mean?” → explain PromQL, show top offenders, show related signals.
- [ ] “Help me build a dashboard for service Y” → propose panels + queries + units + recommended aggregations.

### Assistant capabilities (MVP)
- Natural language → PromQL suggestions (with confidence + alternatives)
- Metric discovery:
  - list candidate metrics by keywords
  - list labels and common label values
  - show example series (label sets)
- Guardrails:
  - validate generated PromQL by executing it (instant/range)
  - enforce safe query patterns (step size, limits, time ranges)
  - warn on high-cardinality queries
- Output helpers:
  - create a Prometheus Graph UI URL from a query
  - render results as table (CLI) + optionally JSON

### Non-functional requirements
- Security/privacy: decide if prompts/metadata can leave the cluster; support running with **local/on-prem LLM** when needed.
- Auth: handle whatever protects our Prometheus (OIDC proxy, mTLS, headers).
- Auditability: log generated queries + who ran them.
- Reliability: deterministic retries; caching of metric/label schema.

---

## 3) Existing tools to evaluate (Open Source first)

### A) Natural language → PromQL (direct)
- **nlpromql** (Go; NL → PromQL; CLI + server API)
  - Repo: https://github.com/PrashantGupta17/nlpromql
- **txt2promql** (Go library + interfaces for text-to-PromQL)
  - Repo: https://github.com/agentkube/txt2promql
- **Kepimetheus** (natural language PromQL; positioned as Grafana-adjacent)
  - Site: https://kepimetheus.github.io/

### B) AI help inside Grafana
- **grafana-llm-app** (Grafana OSS plugin framework for LLM features; can be extended to assist with PromQL)
  - Repo: https://github.com/grafana/grafana-llm-app

### C) “Make dashboards/alerts for me”
- **prom2grafana** (AI-assisted generation of Grafana dashboards + alert rules from Prometheus metrics)
  - Mentioned here: https://www.opensourceprojects.dev/post/1991441801241317398

### D) Adjacent “AI troubleshooting” (not strictly PromQL authoring)
- **K8sGPT** (AI triage for Kubernetes; integrates with Prometheus/observability workflows)
  - Docs: https://k8sgpt.ai/docs/tutorials/observability/
- **Robusta** (+ HolmesGPT option) (enriches Prometheus Alertmanager alerts with context; AI-assisted troubleshooting)
  - Repo: https://github.com/robusta-dev/robusta
  - Prometheus integration docs: https://docs.robusta.dev/master/integrations/prometheus.html

### E) Non-AI but very useful for PromQL building
- **PromLens** (query builder / explainer for PromQL)
  - Site: https://promlens.com/

---

## 4) Can we access an API? (Yes: Prometheus HTTP API)

Official docs: https://prometheus.io/docs/prometheus/latest/querying/api/

### Most-used endpoints
- Instant query:
  - `GET /api/v1/query?query=<promql>`
- Range query:
  - `GET /api/v1/query_range?query=<promql>&start=<rfc3339>&end=<rfc3339>&step=<duration>`
- Label keys:
  - `GET /api/v1/labels`
- Label values:
  - `GET /api/v1/label/<label_name>/values`
- Series discovery:
  - `GET /api/v1/series?match[]=<series_selector>`

### Curl examples
```bash
PROM_URL='https://prometheus.prod.data.platform.smec.services'

# instant query
curl -sG "$PROM_URL/api/v1/query" \
  --data-urlencode 'query=up'

# range query
curl -sG "$PROM_URL/api/v1/query_range" \
  --data-urlencode 'query=rate(http_requests_total[5m])' \
  --data-urlencode 'start=2026-01-14T07:00:00Z' \
  --data-urlencode 'end=2026-01-14T08:00:00Z' \
  --data-urlencode 'step=30s'

# metric discovery helpers
curl -s "$PROM_URL/api/v1/labels"
curl -s "$PROM_URL/api/v1/label/__name__/values" | head
curl -sG "$PROM_URL/api/v1/series" --data-urlencode 'match[]=kube_service_info{namespace="argocd"}'
```

Note: in many setups you’ll need auth headers/cookies; the assistant CLI should support `--header 'Authorization: Bearer …'` and/or `--cookie`.

---

## 5) Is there a command line tool we can use? (Yes)

### A) promtool (ships with Prometheus)
Docs: https://prometheus.io/docs/prometheus/latest/command-line/promtool/

```bash
promtool query instant "$PROM_URL" 'up'
promtool query range "$PROM_URL" 'rate(http_requests_total[5m])' \
  --start 2026-01-14T07:00:00Z --end 2026-01-14T08:00:00Z --step 30s
```

### B) promql-cli (community)
Repo: https://github.com/nalbury/promql-cli

---

## 6) If we build one: suggested approach (pragmatic)

### MVP architecture (CLI-first)
1. **Schema fetch** from Prometheus API:
   - metric names: `/api/v1/label/__name__/values`
   - labels + values (selectively)
   - sample series for candidate metrics
2. **LLM prompt**: provide
   - user intent
   - known metric/label schema snippets
   - house style rules (preferred labels, namespaces, aggregations)
3. **Generate PromQL** + 1–2 alternatives.
4. **Validate** by running the query (instant/range) and checking:
   - parses
   - returns data
   - not too expensive (time range/step/series count)
5. **Return**:
   - PromQL
   - explanation
   - “Open in Graph” link

### UX ideas
- `promassist ask "cpu for argocd last 1h" --prom-url ...`
- `promassist explain '<promql>'`
- `promassist discover kube_service --namespace argocd`
- `promassist open '<promql>'` (prints or opens Graph URL)

### Guardrails we probably want
- Default time window limits (`--range 1h`, `--step 30s`)
- Result limits (`limit=` when supported)
- Detect missing/rare labels and ask clarifying questions
- Prefer recording rules / standardized metrics when available

---

## 7) Request & idea backlog (fill this as we learn)

### Requests (user-facing)
- [ ] NL → PromQL for “golden paths” (CPU/mem/restarts/errors/latency per service)
- [ ] Suggest the *right* metric when multiple exist (e.g., app vs ingress vs mesh)
- [ ] Explain what a query does in plain language
- [ ] Detect common PromQL mistakes (rate windows, wrong aggregation, label joins)
- [ ] Create “starter dashboards” per namespace/service

### Ideas (implementation)
- [ ] Curated prompt snippets per domain (kube-state-metrics, node-exporter, ingress, JVM)
- [ ] RAG over internal runbooks + alert descriptions + SLOs
- [ ] Save/share queries as short links (with metadata, owner, last validated)
- [ ] Add a “query linter” mode (best practices + performance)

### Open questions
- [ ] What auth protects the prod Prometheus endpoint (OIDC, basic auth, mTLS, IP allowlist)?
- [ ] Do we have a separate read-only Prometheus for exploration?
- [ ] Which labels are standard in our org (`namespace`, `service`, `app`, `cluster`, `team`)?
- [ ] Do we want to support multiple backends (Thanos/Cortex/Mimir) as well?

---

## 8) Next steps
1. Pick 1–2 OSS candidates (e.g., `nlpromql`, `txt2promql`) and run a quick spike against our Prometheus.
2. Define a short “golden query set” (10–20 queries) we want the assistant to reliably produce.
3. Decide packaging: CLI-first (fastest) vs Grafana plugin vs Slack bot.
