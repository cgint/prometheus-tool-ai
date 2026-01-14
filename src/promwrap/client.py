from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

Json = Dict[str, Any]


class PromwrapError(Exception):
    def __init__(self, code: str, message: str, details: Optional[Json] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details: Json = details or {}


@dataclass
class PromwrapConfig:
    base_url: str
    timeout_seconds: float = 10.0

    # guardrails
    max_range_seconds: int = 6 * 3600
    min_step_seconds: int = 10
    max_points: int = 11_000

    # auth
    auth_header: Optional[str] = None  # e.g. "Bearer …" or "Basic …"
    headers: Dict[str, str] = field(default_factory=dict)
    cookie: Optional[str] = None

    # tls
    ca_file: Optional[str] = None
    cert_file: Optional[str] = None
    key_file: Optional[str] = None
    insecure_skip_verify: bool = False


def _parse_rfc3339(s: str) -> datetime:
    # Prometheus commonly uses RFC3339 with 'Z'.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as e:
        raise PromwrapError("INVALID_ARGUMENT", f"Invalid RFC3339 timestamp: {s}", {"value": s}) from e
    if dt.tzinfo is None:
        # Treat naive inputs as UTC.
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_lookback(s: str, now: Optional[datetime] = None) -> datetime:
    # supports e.g. 10s, 5m, 1h, 2d
    now = now or datetime.now(timezone.utc)
    unit = s[-1]
    try:
        value = int(s[:-1])
    except ValueError as e:
        raise PromwrapError("INVALID_ARGUMENT", f"Invalid lookback duration: {s}", {"value": s}) from e

    delta: timedelta
    if unit == "s":
        delta = timedelta(seconds=value)
    elif unit == "m":
        delta = timedelta(minutes=value)
    elif unit == "h":
        delta = timedelta(hours=value)
    elif unit == "d":
        delta = timedelta(days=value)
    else:
        raise PromwrapError(
            "INVALID_ARGUMENT",
            f"Invalid lookback duration unit (expected s|m|h|d): {s}",
            {"value": s},
        )
    return now - delta


def _ensure_base_url(url: str) -> str:
    url = url.strip()
    if not url:
        raise PromwrapError("CONFIG_ERROR", "base_url is required")
    return url.rstrip("/") + "/"


class PromClient:
    def __init__(self, cfg: PromwrapConfig):
        self.cfg = cfg
        self._base = _ensure_base_url(cfg.base_url)

    # --- low-level ---
    def _ssl_context(self) -> ssl.SSLContext:
        if self.cfg.insecure_skip_verify:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        else:
            ctx = ssl.create_default_context()

        if self.cfg.ca_file:
            ctx.load_verify_locations(cafile=self.cfg.ca_file)
        if self.cfg.cert_file:
            ctx.load_cert_chain(certfile=self.cfg.cert_file, keyfile=self.cfg.key_file)
        return ctx

    def _request(self, path: str, params: Optional[Dict[str, Any]] = None) -> Json:
        url = urllib.parse.urljoin(self._base, path.lstrip("/"))
        if params:
            # doseq supports repeated keys (e.g. match[]).
            q = urllib.parse.urlencode(params, doseq=True)
            url = f"{url}?{q}"

        headers: Dict[str, str] = {"Accept": "application/json"}
        headers.update(self.cfg.headers or {})
        if self.cfg.auth_header:
            headers["Authorization"] = self.cfg.auth_header
        if self.cfg.cookie:
            headers["Cookie"] = self.cfg.cookie

        req = urllib.request.Request(url=url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.timeout_seconds, context=self._ssl_context()) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8")
            except Exception:
                body = ""
            raise PromwrapError(
                "PROMETHEUS_ERROR",
                f"HTTP {e.code} from Prometheus",
                {"url": url, "status": e.code, "body": body[:2000]},
            ) from e
        except urllib.error.URLError as e:
            raise PromwrapError("NETWORK_ERROR", "Network error calling Prometheus", {"url": url, "error": str(e)}) from e

        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            raise PromwrapError(
                "PROMETHEUS_ERROR",
                "Non-JSON response from Prometheus",
                {"url": url, "body": body[:2000]},
            ) from e

        # Prometheus API convention: {"status": "success"|"error", ...}
        if isinstance(data, dict) and data.get("status") == "error":
            raise PromwrapError(
                "PROMETHEUS_ERROR",
                data.get("error", "Prometheus returned status=error"),
                {"url": url, "errorType": data.get("errorType"), "warnings": data.get("warnings")},
            )

        return data

    # --- status / info ---
    def ready(self) -> bool:
        # /-/ready is not JSON, so keep it simple.
        url = urllib.parse.urljoin(self._base, "-/ready")
        req = urllib.request.Request(url=url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.timeout_seconds, context=self._ssl_context()) as resp:
                return resp.status == 200
        except Exception:
            return False

    def buildinfo(self) -> Json:
        return self._request("/api/v1/status/buildinfo")

    # --- discovery ---
    def metric_names(self) -> List[str]:
        j = self._request("/api/v1/label/__name__/values")
        return list(j.get("data", []))

    def label_names(self) -> List[str]:
        j = self._request("/api/v1/labels")
        return list(j.get("data", []))

    def label_values(self, label: str) -> List[str]:
        if not label:
            raise PromwrapError("INVALID_ARGUMENT", "label is required")
        j = self._request(f"/api/v1/label/{urllib.parse.quote(label)}/values")
        return list(j.get("data", []))

    # --- querying ---
    def query_instant(self, promql: str, *, time_rfc3339: Optional[str] = None, dedup: Optional[bool] = None) -> Json:
        if not promql:
            raise PromwrapError("INVALID_ARGUMENT", "promql is required")
        params: Dict[str, Any] = {"query": promql}
        if time_rfc3339:
            _parse_rfc3339(time_rfc3339)
            params["time"] = time_rfc3339
        if dedup is not None:
            params["dedup"] = "true" if dedup else "false"
        return self._request("/api/v1/query", params)

    def query_range(
        self,
        promql: str,
        *,
        start_rfc3339: str,
        end_rfc3339: str,
        step_seconds: int,
        dedup: Optional[bool] = None,
    ) -> Json:
        if not promql:
            raise PromwrapError("INVALID_ARGUMENT", "promql is required")

        start = _parse_rfc3339(start_rfc3339)
        end = _parse_rfc3339(end_rfc3339)
        if end <= start:
            raise PromwrapError(
                "INVALID_ARGUMENT",
                "end must be after start",
                {"start": start_rfc3339, "end": end_rfc3339},
            )

        if step_seconds < self.cfg.min_step_seconds:
            raise PromwrapError(
                "GUARDRAIL_VIOLATION",
                "step too small",
                {"min_step_seconds": self.cfg.min_step_seconds, "requested_step_seconds": step_seconds},
            )

        range_seconds = int((end - start).total_seconds())
        if range_seconds > self.cfg.max_range_seconds:
            raise PromwrapError(
                "GUARDRAIL_VIOLATION",
                "range too large",
                {"max_range_seconds": self.cfg.max_range_seconds, "requested_range_seconds": range_seconds},
            )

        points = int(range_seconds / step_seconds) + 1
        if points > self.cfg.max_points:
            raise PromwrapError(
                "GUARDRAIL_VIOLATION",
                "too many datapoints",
                {"max_points": self.cfg.max_points, "requested_points": points},
            )

        params: Dict[str, Any] = {
            "query": promql,
            "start": start_rfc3339,
            "end": end_rfc3339,
            "step": str(step_seconds),
        }
        if dedup is not None:
            params["dedup"] = "true" if dedup else "false"
        return self._request("/api/v1/query_range", params)

    def series(
        self,
        match: List[str],
        *,
        start_rfc3339: Optional[str] = None,
        end_rfc3339: Optional[str] = None,
        max_series: Optional[int] = None,
    ) -> List[Json]:
        if not match:
            raise PromwrapError("GUARDRAIL_VIOLATION", "series requires at least one match[] selector")

        params: Dict[str, Any] = {"match[]": match}
        if start_rfc3339:
            _parse_rfc3339(start_rfc3339)
            params["start"] = start_rfc3339
        if end_rfc3339:
            _parse_rfc3339(end_rfc3339)
            params["end"] = end_rfc3339

        j = self._request("/api/v1/series", params)
        data = j.get("data", [])
        if not isinstance(data, list):
            raise PromwrapError("PROMETHEUS_ERROR", "Unexpected series response", {"response": j})
        if max_series is not None:
            return data[:max_series]
        return data


def resolve_time(s: str, *, now: Optional[datetime] = None) -> str:
    """Accept RFC3339 or 'now' or a lookback like '1h' (for CLI convenience)."""
    now = now or datetime.now(timezone.utc)
    if s == "now":
        return now.isoformat().replace("+00:00", "Z")
    if len(s) >= 2 and s[-1] in {"s", "m", "h", "d"} and s[:-1].isdigit():
        return _parse_lookback(s, now=now).isoformat().replace("+00:00", "Z")
    return _parse_rfc3339(s).isoformat().replace("+00:00", "Z")


def parse_step_seconds(step: str) -> int:
    if step.endswith("s") and step[:-1].isdigit():
        return int(step[:-1])
    if step.endswith("m") and step[:-1].isdigit():
        return int(step[:-1]) * 60
    if step.endswith("h") and step[:-1].isdigit():
        return int(step[:-1]) * 3600
    raise PromwrapError("INVALID_ARGUMENT", f"Invalid step duration: {step}", {"value": step})
