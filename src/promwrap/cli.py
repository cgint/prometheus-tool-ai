from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, List

from promwrap.client import PromClient, PromwrapConfig, PromwrapError, parse_step_seconds, resolve_time


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True))


def _filter_regex(values: List[str], pattern: str | None) -> List[str]:
    if not pattern:
        return values
    rx = re.compile(pattern)
    return [v for v in values if rx.search(v)]


def _make_client(args: argparse.Namespace) -> PromClient:
    url = args.url or os.getenv("PROM_URL")
    if not url:
        raise PromwrapError("CONFIG_ERROR", "Missing Prometheus URL (use --url or PROM_URL env var)")

    cfg = PromwrapConfig(
        base_url=url,
        timeout_seconds=float(args.timeout),
        auth_header=args.auth_header,
        cookie=args.cookie,
        insecure_skip_verify=bool(args.insecure_skip_verify),
        ca_file=args.ca_file,
        cert_file=args.cert_file,
        key_file=args.key_file,
    )

    if args.header:
        for h in args.header:
            if ":" not in h:
                raise PromwrapError("INVALID_ARGUMENT", "Invalid header (expected 'Name: value')", {"header": h})
            k, v = h.split(":", 1)
            cfg.headers[k.strip()] = v.strip()

    return PromClient(cfg)


def main(argv: List[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="promwrap", description="Minimal Prometheus HTTP API wrapper")
    p.add_argument("--url", help="Prometheus base URL (or env PROM_URL)")
    p.add_argument("--timeout", default="10", help="HTTP timeout seconds")
    p.add_argument("--output", choices=["json", "table"], default="table")

    p.add_argument("--auth-header", help="Full Authorization header value, e.g. 'Bearer …'")
    p.add_argument("--header", action="append", help="Extra header, repeatable: 'Name: value'")
    p.add_argument("--cookie", help="Cookie header value")

    p.add_argument("--ca-file")
    p.add_argument("--cert-file")
    p.add_argument("--key-file")
    p.add_argument("--insecure-skip-verify", action="store_true")

    # Allow "global" flags after the subcommand by also registering them on subparsers.
    # Use SUPPRESS defaults so that values provided before the subcommand aren't overwritten.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--url", default=argparse.SUPPRESS)
    common.add_argument("--timeout", default=argparse.SUPPRESS)
    common.add_argument("--output", choices=["json", "table"], default=argparse.SUPPRESS)
    common.add_argument("--auth-header", default=argparse.SUPPRESS)
    common.add_argument("--header", action="append", default=argparse.SUPPRESS)
    common.add_argument("--cookie", default=argparse.SUPPRESS)
    common.add_argument("--ca-file", default=argparse.SUPPRESS)
    common.add_argument("--cert-file", default=argparse.SUPPRESS)
    common.add_argument("--key-file", default=argparse.SUPPRESS)
    common.add_argument("--insecure-skip-verify", action="store_true", default=argparse.SUPPRESS)

    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ping", parents=[common])
    sub.add_parser("buildinfo", parents=[common])

    sp = sub.add_parser("metrics", parents=[common])
    sp.add_argument("--match", dest="match", help="Regex filter (client-side)")
    sp.add_argument("--limit", type=int, default=0)

    sp = sub.add_parser("labels", parents=[common])
    sp.add_argument("--limit", type=int, default=0)

    sp = sub.add_parser("label-values", parents=[common])
    sp.add_argument("label")
    sp.add_argument("--match", dest="match", help="Regex filter (client-side)")
    sp.add_argument("--limit", type=int, default=0)

    sp = sub.add_parser("query", parents=[common])
    sp.add_argument("promql")
    sp.add_argument("--time", default="now", help="RFC3339 or 'now'")

    sp = sub.add_parser("range", parents=[common])
    sp.add_argument("promql")
    sp.add_argument("--start", required=True, help="RFC3339 or lookback like 1h")
    sp.add_argument("--end", default="now", help="RFC3339 or 'now'")
    sp.add_argument("--step", default="30s", help="step duration like 30s, 1m")

    sp = sub.add_parser("series", parents=[common])
    sp.add_argument("--match", dest="match", action="append", required=True, help="PromQL selector, repeatable")
    sp.add_argument("--start")
    sp.add_argument("--end")
    sp.add_argument("--max-series", type=int)

    args = p.parse_args(argv)

    try:
        client = _make_client(args)

        if args.cmd == "ping":
            ok = client.ready()
            if args.output == "json":
                _print_json({"ok": ok})
            else:
                print("ok" if ok else "not-ready")
            return

        if args.cmd == "buildinfo":
            out = client.buildinfo()
            if args.output == "json":
                _print_json(out)
            else:
                d = (out.get("data") or {})
                print(f"version={d.get('version')} revision={d.get('revision')} buildDate={d.get('buildDate')}")
            return

        if args.cmd == "metrics":
            vals = _filter_regex(client.metric_names(), args.match)
            if args.limit:
                vals = vals[: args.limit]
            if args.output == "json":
                _print_json(vals)
            else:
                print("\n".join(vals))
            return

        if args.cmd == "labels":
            vals = client.label_names()
            if args.limit:
                vals = vals[: args.limit]
            if args.output == "json":
                _print_json(vals)
            else:
                print("\n".join(vals))
            return

        if args.cmd == "label-values":
            vals = _filter_regex(client.label_values(args.label), args.match)
            if args.limit:
                vals = vals[: args.limit]
            if args.output == "json":
                _print_json(vals)
            else:
                print("\n".join(vals))
            return

        if args.cmd == "query":
            t = resolve_time(args.time, now=datetime.now(timezone.utc))
            out = client.query_instant(args.promql, time_rfc3339=t)
            if args.output == "json":
                _print_json(out)
            else:
                _print_json(out.get("data"))
            return

        if args.cmd == "range":
            now = datetime.now(timezone.utc)
            start = resolve_time(args.start, now=now)
            end = resolve_time(args.end, now=now)
            step = parse_step_seconds(args.step)
            out = client.query_range(args.promql, start_rfc3339=start, end_rfc3339=end, step_seconds=step)
            if args.output == "json":
                _print_json(out)
            else:
                _print_json(out.get("data"))
            return

        if args.cmd == "series":
            out = client.series(args.match, start_rfc3339=args.start, end_rfc3339=args.end, max_series=args.max_series)
            _print_json(out) if args.output == "json" else print(json.dumps(out, indent=2, sort_keys=True))
            return

    except PromwrapError as e:
        if getattr(args, "output", "table") == "json":
            _print_json({"ok": False, "error": {"code": e.code, "message": e.message, "details": e.details}})
        else:
            print(f"ERROR [{e.code}]: {e.message}", file=sys.stderr)
        raise SystemExit(1) from e
