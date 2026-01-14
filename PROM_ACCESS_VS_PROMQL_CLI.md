# PROM access vs promql-cli — short comparison

Context:
- Target Prometheus: `https://prometheus.prod.data.platform.smec.services`
- Access probe results are in `PROM_ACCESS_FINDINGD.md`.
- promql-cli repo analysis is in `REPO_PROM_CLI_WORTH.md`.

## What our access findings imply (facts)
From `PROM_ACCESS_FINDINGD.md`:
- Core HTTP API endpoints are reachable **without additional auth** (at least from this environment):
  - `/api/v1/status/buildinfo` → 200
  - `/api/v1/labels` → 200
  - `/api/v1/label/__name__/values` → 200
- `promtool` (Homebrew) can run instant queries successfully (`up`, `count(up)`).

## Tool comparison (relevant to the above)
| Topic | promtool (brew Prometheus) | promql-cli (nalbury/promql-cli) |
|---|---|---|
| Works with current access situation | ✅ already proven in findings | ✅ should work too (same HTTP API), but not tested here |
| Best endpoint for metric discovery | ✅ can use HTTP API (or direct curl) with `/label/__name__/values` | ⚠️ `promql metrics` uses **/series** (can be heavier than `/label/__name__/values`) |
| Output UX | OK (raw-ish output) | ✅ nice table + ASCII graphs + csv/json |
| Enterprise HTTP config | ✅ `--http.config.file` (richer/more standard) | ⚠️ mainly `Authorization:` header + TLS flags |
| Maintenance | ✅ Prometheus upstream | ⚠️ last activity seen: 2022 |

## Conclusion
Given we **already have working access** and `promtool` works, the best path for the assistant MVP is **promtool + direct Prometheus HTTP API** (especially for discovery via `/label/__name__/values`).

`promql-cli` is only “worth it” as an optional *developer convenience* for terminal-friendly output (ASCII graphs / tables), but it should not be the primary dependency or the basis for discovery logic.
