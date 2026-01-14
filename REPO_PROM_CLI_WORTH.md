# promql-cli (nalbury/promql-cli) — worth using?

> Note: `PROMETHEUS_ASSISTANT.md` mentions **promql-cli** (not “prometheus-cli”). I cloned `https://github.com/nalbury/promql-cli` into `./promql-cli/`.

## What it is
`promql-cli` is a small Go CLI (binary name: `promql`) that queries the Prometheus HTTP API and prints:
- **Instant queries** as a tabular output (or JSON/CSV)
- **Range queries** as **ASCII graphs** per time series (or JSON/CSV)
- Simple discovery helpers:
  - `promql metrics [selector]` (lists metric names; implemented via the **/series** API and extracting `__name__`)
  - `promql labels <query>` (returns labels present in the query result)
  - `promql meta [metric]` (Prometheus metadata: type/help/unit)

Implementation highlights (from code):
- Uses `github.com/prometheus/client_golang/api/prometheus/v1` (same upstream API client library many Go tools use).
- Auth is **only** via `Authorization: <type> <credentials>` (credentials can be provided directly or read from a file).
- TLS client options are supported (CA/cert/key/servername/insecure).
- Config via `$HOME/.promql-cli.yaml` plus env vars (`PROMQL_*`) via Viper.
- Last release/tag seen in the clone: `v0.3.0`, last commit date: **2022-12-31**.

License: Apache-2.0.

## What the Homebrew “Prometheus tool” (promtool) already gives us
Homebrew’s Prometheus package includes `promtool`, which (in current Prometheus) supports:
- `promtool query instant|range|series|labels …`
- robust HTTP client configuration via `--http.config.file` (covers more enterprise setups cleanly)
- additional non-query features (rule checking, config checking, etc.)

## Comparison: promql-cli vs promtool (for our use case)
### Where promql-cli is better
- **UX for humans in a terminal**:
  - range queries rendered as **ASCII graphs** (fast “shape of the data” feedback)
  - instant vectors printed as a nice table
- **Quick export**: `--output json|csv` is straightforward.
- Convenience commands: `metrics`, `meta` are handy for discovery without remembering endpoints.

### Where promtool is better
- **Maintenance / longevity**: `promtool` is maintained as part of Prometheus; `promql-cli` looks relatively inactive (last change 2022).
- **HTTP/auth flexibility**: `promtool --http.config.file` supports richer configs (and tends to match real-world setups better than “just Authorization header”).
- **Less extra dependency surface**: we likely already have Prometheus installed via brew.
- **No naming confusion**: `promql-cli` installs a binary named `promql`, which can be confusing (PromQL is a language), and could conflict with our own CLI naming.

### Gaps / caveats in promql-cli
- “Metric discovery” (`promql metrics`) is implemented by calling **Series** with a default selector `{job=~".+"}` and extracting `__name__`.
  - This can be **heavy** on big Prometheus servers and depends on retention/TSDB state.
  - It’s not the same as using `/api/v1/label/__name__/values`.
- No built-in guardrails around high-cardinality queries (beyond a timeout).
- ASCII graph sizing uses `stty size` (can fail in non-interactive contexts).

## Is it a benefit for the Prometheus Assistant project?
If our goal is a **human-friendly terminal explorer** right now, `promql-cli` is a nice “batteries included” UX baseline (table + ascii graphs + csv/json).

But for the assistant described in `PROMETHEUS_ASSISTANT.md` (intent → discovery → validated query with guardrails), `promql-cli` is **not a strong foundation**:
- It’s primarily a CLI wrapper, not a reusable library with stable APIs.
- We will still need custom logic (schema caching, safe defaults, high-cardinality detection, URL generation, auth/cookies/proxies, etc.).
- `promtool` plus direct Prometheus HTTP API calls already cover the core query execution and validation needs.

## Recommendation
**Do not adopt `promql-cli` as the primary base tool** over Homebrew’s Prometheus `promtool`.

Use it optionally as:
1) a **developer convenience tool** for quick ad-hoc exploration (especially range-query ascii graphs), or
2) inspiration for output formatting (table/graph/CSV/JSON) if we build our own CLI.

For the assistant MVP, prefer:
- direct Prometheus HTTP API calls (for metric/label discovery endpoints), and/or
- `promtool query …` as the validator/executor (especially if we want to leverage `--http.config.file`).

## If we still want to trial it (low-effort)
- Build/run locally:
  - `cd promql-cli && make build` (or `go build ./...`)
- Try against our Prometheus:
  - `./promql --host "$PROM_URL" 'up'`
  - `./promql --host "$PROM_URL" 'rate(http_requests_total[5m])' --start 1h`
- If auth is required:
  - `./promql --auth-type Bearer --auth-credentials-file <tokenfile> …`

Success criterion for keeping it around: it must work with our real auth/TLS setup and not encourage expensive discovery patterns (series-heavy queries) on prod.
