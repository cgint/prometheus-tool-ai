# TASK_WRAPPER_SPEC — Prometheus API Wrapper (Python)

Goal: provide a **safe, minimal, agent-friendly** wrapper around the **Prometheus HTTP API** with a small CLI for humans.

This is a *spec* (interface/behavior). Implementation can be done as a Python package + console script.

---

## 1) Scope

### In scope (MVP)
- Query execution:
  - instant queries (`/api/v1/query`)
  - range queries (`/api/v1/query_range`)
- Discovery:
  - metric names (`/api/v1/label/__name__/values`)
  - label keys (`/api/v1/labels`)
  - label values (`/api/v1/label/<name>/values`)
  - series lookup (`/api/v1/series`) but guarded (optional/limited)
- Basic metadata:
  - buildinfo (`/api/v1/status/buildinfo`)
  - runtime info (optional) (`/api/v1/status/runtimeinfo`)
- Output formats suitable for:
  - humans (pretty table)
  - machines/agents (JSON)

### Explicit non-goals (MVP)
- Writing/updating rules, remote-write, admin endpoints
- Grafana dashboard generation
- Full PromQL linting/optimization (we can add later)

---

## 2) Safety / Guardrails (must-have)

The wrapper MUST enforce these defaults unless explicitly overridden by a trusted caller:

- **Max range window**: e.g. `max_range_seconds = 6h` (configurable)
- **Min step**: e.g. `min_step_seconds = 10s` (configurable)
- **Max datapoints**: `((end-start)/step) <= max_points` (e.g. 11k)
- **Timeout**: default `10s`, max `30s` unless configured
- **Query allow/deny** (simple rules):
  - deny direct `series` calls without a match selector
  - optionally deny regex selectors like `=~".*"` for high-risk labels unless `--allow-risky`
- **Result size limit**:
  - limit number of returned series displayed (for CLI)
  - for agent JSON, return full data by default but allow `--max-series` to truncate

Guardrail failures MUST return a structured error (see §6).

---

## 3) Configuration and Auth

### Configuration sources (priority order)
1. CLI flags
2. Environment variables
3. Config file (`~/.promwrap.yaml` or `./promwrap.yaml`)

### Required config
- `PROM_URL` (base URL), e.g. `https://prometheus.prod.data.platform.smec.services`

### Auth options
We keep it minimal but practical:
- `Authorization` header:
  - `--auth-type Bearer|Basic`
  - `--auth-credentials <string>` (already base64 if Basic)
  - `--auth-credentials-file <path>`
- Optional custom headers (for proxies):
  - repeatable `--header 'Name: value'`
- Optional cookie:
  - `--cookie 'name=value; name2=value2'` or `--cookie-file <path>`

### TLS options
- `--ca-file`, `--cert-file`, `--key-file`
- `--insecure-skip-verify`

---

## 4) Python API (library) — Proposed Interface

Package name: `promwrap`

### Core types

```python
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Union

Json = Dict[str, Any]

@dataclass
class PromwrapConfig:
    base_url: str
    timeout_seconds: float = 10.0

    # guardrails
    max_range_seconds: int = 6 * 3600
    min_step_seconds: int = 10
    max_points: int = 11000

    # auth
    auth_header: Optional[str] = None  # e.g. "Bearer …" or "Basic …"
    headers: Dict[str, str] = None
    cookie: Optional[str] = None

    # tls
    ca_file: Optional[str] = None
    cert_file: Optional[str] = None
    key_file: Optional[str] = None
    insecure_skip_verify: bool = False


class PromwrapError(Exception):
    code: str
    message: str
    details: Json
```

### Client surface

```python
class PromClient:
    def __init__(self, cfg: PromwrapConfig): ...

    # --- status / info ---
    def buildinfo(self) -> Json: ...

    # --- discovery ---
    def metric_names(self) -> List[str]: ...
    def label_names(self) -> List[str]: ...
    def label_values(self, label: str) -> List[str]: ...

    # --- querying ---
    def query_instant(
        self,
        promql: str,
        *,
        time_rfc3339: Optional[str] = None,
        dedup: Optional[bool] = None,
    ) -> Json: ...

    def query_range(
        self,
        promql: str,
        *,
        start_rfc3339: str,
        end_rfc3339: str,
        step_seconds: int,
        dedup: Optional[bool] = None,
    ) -> Json: ...

    # optional, guarded
    def series(
        self,
        match: List[str],
        *,
        start_rfc3339: Optional[str] = None,
        end_rfc3339: Optional[str] = None,
        max_series: Optional[int] = None,
    ) -> List[Json]: ...
```

### Return shapes
- The library SHOULD return the **raw Prometheus JSON** for query calls (`query_instant`, `query_range`) so agents get stable structured data.
- Convenience helpers MAY be added later to map to typed objects.

---

## 5) CLI — Minimal UX

Binary name: `promwrap`

### Global flags
- `--url <PROM_URL>` (or env `PROM_URL`)
- `--timeout <seconds>`
- Auth/TLS flags from §3
- Output:
  - `--output json|table` (default: `table` for humans)
  - `--raw` (print raw JSON even when `--output table` would otherwise format)

### Commands

#### `promwrap ping`
- Calls `/-/ready` (or `buildinfo`) to confirm connectivity.

#### `promwrap buildinfo`
- Prints `/api/v1/status/buildinfo`.

#### `promwrap metrics [--match <regex>] [--limit N]`
- Uses `/api/v1/label/__name__/values`
- `--match` filters client-side (regex), default none.

#### `promwrap labels [--limit N]`
- Uses `/api/v1/labels`

#### `promwrap label-values <label> [--match <regex>] [--limit N]`
- Uses `/api/v1/label/<label>/values`

#### `promwrap query <promql> [--time <rfc3339>]`
- Instant query (`/api/v1/query`)

#### `promwrap range <promql> --start <rfc3339|lookback> --end <rfc3339|now> --step <duration>`
- Range query (`/api/v1/query_range`)
- Allowed shorthand:
  - `--start 1h` meaning `now-1h`
  - `--end now` default
  - `--step 30s` parsed to seconds

#### `promwrap series --match '<selector>' [--start ...] [--end ...] [--max-series N]`
- Uses `/api/v1/series`
- MUST require at least one `--match`.

### CLI examples (based on our proven endpoint)

```bash
PROM_URL='https://prometheus.prod.data.platform.smec.services'

promwrap --url "$PROM_URL" buildinfo --output json

promwrap --url "$PROM_URL" metrics --match 'kube_.*' --limit 50

promwrap --url "$PROM_URL" query 'count(up)'

promwrap --url "$PROM_URL" range 'sum(rate(http_requests_total[5m])) by (namespace)' \
  --start 1h --end now --step 30s --output json
```

---

## 6) Error model (important for agents)

All failures should be machine-readable.

### Library
Raise `PromwrapError` with:
- `code` (string enum)
- `message` (human)
- `details` (structured, safe to log)

Suggested `code` values:
- `CONFIG_ERROR`
- `AUTH_ERROR`
- `NETWORK_ERROR`
- `PROMETHEUS_ERROR` (non-2xx or `{status:"error"}`)
- `GUARDRAIL_VIOLATION`
- `INVALID_ARGUMENT`

### CLI
- Exit code non-zero
- If `--output json`, print error as JSON:

```json
{
  "ok": false,
  "error": {
    "code": "GUARDRAIL_VIOLATION",
    "message": "range too large",
    "details": {"max_range_seconds": 21600, "requested_range_seconds": 86400}
  }
}
```

---

## 7) Implementation notes (so we don’t paint ourselves into a corner)

- Prefer `httpx` (sync) or `requests` for HTTP; keep dependencies minimal.
- All HTTP calls should be made via one internal method:
  - adds headers/auth/cookies
  - applies timeout
  - validates `{status: success|error}`
- Add a small parser for durations (`10s`, `5m`, `1h`) and RFC3339 times.
- Keep caching optional (later): metric names + label names cached in memory for N minutes.

---

## 8) Success criteria (MVP)

- From a clean machine with only `python` installed, user can:
  - run `promwrap buildinfo`
  - list metrics/labels
  - run `query` and `range` safely (guardrails enforced)
  - get JSON output that an AI agent can consume without parsing tables
