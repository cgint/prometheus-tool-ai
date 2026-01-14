from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from constants import PROM_URL
from promwrap import PromClient, PromwrapConfig
from promwrap.client import parse_step_seconds, resolve_time


def _client() -> PromClient:
    return PromClient(PromwrapConfig(base_url=PROM_URL))


def prom_buildinfo() -> Dict[str, Any]:
    """Retrieve Prometheus server version and build metadata. Use this to verify the server environment and capabilities.

    Returns the raw Prometheus JSON response including version, revision, and build date.
    """
    return _client().buildinfo()


def prom_metrics(match_regex: Optional[str] = None, limit: int = 50) -> List[str]:
    """List available metric names, filtered by an optional regex. Use this to discover what data is available for querying.

    - match_regex: Optional regex to filter metric names (e.g., '.*http.*').
    - limit: Max number of names to return (default 50, <=0 for unlimited).
    """
    metrics = _client().metric_names()
    if match_regex:
        import re

        rx = re.compile(match_regex)
        metrics = [m for m in metrics if rx.search(m)]
    return metrics[:limit] if limit > 0 else metrics


def prom_labels(limit: int = 50) -> List[str]:
    """List all unique label names across all time series. Use this to understand available dimensions for filtering queries.

    - limit: Max number of label names to return (default 50, <=0 for unlimited).
    """
    labels = _client().label_names()
    return labels[:limit] if limit > 0 else labels


def prom_label_values(label: str, match_regex: Optional[str] = None, limit: int = 50) -> List[str]:
    """List all unique values for a specific label name. Use this to find valid filter values for PromQL queries (e.g., job names, instance IDs).

    - label: The label name to fetch values for (e.g., 'job', 'instance').
    - match_regex: Optional regex to filter the returned values.
    - limit: Max number of values to return (default 50, <=0 for unlimited).
    """
    values = _client().label_values(label)
    if match_regex:
        import re

        rx = re.compile(match_regex)
        values = [v for v in values if rx.search(v)]
    return values[:limit] if limit > 0 else values


def prom_query(promql: str, time: str = "now") -> Dict[str, Any]:
    """Execute an instant PromQL query at a single point in time. Use this for current status, alerts, or single-value aggregations.

    - promql: The PromQL expression to evaluate.
    - time: Evaluation time (RFC3339, "now", or offset like "1h").
    """
    t = resolve_time(time, now=datetime.now(timezone.utc))
    return _client().query_instant(promql, time_rfc3339=t)


def prom_range(promql: str, start: str, end: str = "now", step: str = "30s") -> Dict[str, Any]:
    """Execute a PromQL query over a range of time. Use this to analyze trends, patterns, and historical data over a specified interval.

    - promql: The PromQL expression to evaluate.
    - start: Start of the time range (RFC3339, "now", or offset like "1h").
    - end: End of the time range (default "now").
    - step: Query resolution step (e.g., "15s", "1m", "5m").
    """
    now = datetime.now(timezone.utc)
    s = resolve_time(start, now=now)
    e = resolve_time(end, now=now)
    step_seconds = parse_step_seconds(step)
    return _client().query_range(promql, start_rfc3339=s, end_rfc3339=e, step_seconds=step_seconds)

