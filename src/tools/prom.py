from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from constants import PROM_URL
from promwrap import PromClient, PromwrapConfig
from promwrap.client import parse_step_seconds, resolve_time


def _client() -> PromClient:
    return PromClient(PromwrapConfig(base_url=PROM_URL))


def prom_buildinfo() -> Dict[str, Any]:
    """Fetch Prometheus server build metadata (version/revision/buildDate/goVersion) via /api/v1/status/buildinfo.

    Returns the raw Prometheus JSON response, typically:
    {"status": "success", "data": {...}}.
    """
    return _client().buildinfo()


def prom_metrics(match_regex: Optional[str] = None, limit: int = 50) -> List[str]:
    """List metric names from prometheus

    - match_regex: optional client-side regex filter applied to returned names.
    - limit: max number of names to return (use <=0 for no limit).

    Returns: List[str]
    """
    metrics = _client().metric_names()
    if match_regex:
        import re

        rx = re.compile(match_regex)
        metrics = [m for m in metrics if rx.search(m)]
    return metrics[:limit] if limit > 0 else metrics


def prom_labels(limit: int = 50) -> List[str]:
    """List label names from /api/v1/labels.

    - limit: max number of label names to return (use <=0 for no limit).

    Returns: List[str]
    """
    labels = _client().label_names()
    return labels[:limit] if limit > 0 else labels


def prom_label_values(label: str, match_regex: Optional[str] = None, limit: int = 50) -> List[str]:
    """List values for a label from /api/v1/label/<label>/values.

    - label: label name to query values for (e.g. "job", "namespace").
    - match_regex: optional client-side regex filter applied to returned values.
    - limit: max number of values to return (use <=0 for no limit).

    Returns: List[str]
    """
    values = _client().label_values(label)
    if match_regex:
        import re

        rx = re.compile(match_regex)
        values = [v for v in values if rx.search(v)]
    return values[:limit] if limit > 0 else values


def prom_query(promql: str, time: str = "now") -> Dict[str, Any]:
    """Run an instant PromQL query via /api/v1/query.

    - promql: PromQL expression.
    - time: RFC3339 timestamp, "now", or a lookback like "1h".

    Returns the raw Prometheus JSON response.
    For vector results, rows are in resp["data"]["result"], with labels in row["metric"].
    """
    t = resolve_time(time, now=datetime.now(timezone.utc))
    return _client().query_instant(promql, time_rfc3339=t)


def prom_range(promql: str, start: str, end: str = "now", step: str = "30s") -> Dict[str, Any]:
    """Run a range PromQL query via /api/v1/query_range.

    - promql: PromQL expression.
    - start/end: RFC3339, "now", or lookback like "1h".
    - step: duration like "30s", "1m", "1h".

    Returns the raw Prometheus JSON response (matrix data in resp["data"]["result"]).
    Guardrails apply (min step, max range, max points).
    """
    now = datetime.now(timezone.utc)
    s = resolve_time(start, now=now)
    e = resolve_time(end, now=now)
    step_seconds = parse_step_seconds(step)
    return _client().query_range(promql, start_rfc3339=s, end_rfc3339=e, step_seconds=step_seconds)

