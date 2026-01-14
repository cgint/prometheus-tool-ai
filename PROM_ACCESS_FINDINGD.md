# PROM Access Findings

Date: 2026-01-14T08:32:46Z
Target: https://prometheus.prod.data.platform.smec.services

## Local tools
```
promtool: /opt/homebrew/bin/promtool
promtool, version 3.9.1 (branch: non-git, revision: non-git)
  build user:       reproducible@reproducible
  build date:       20260107-16:05:27
  go version:       go1.25.5
  platform:         darwin/arm64
  tags:             netgo,builtinassets

curl 8.7.1 (x86_64-apple-darwin25.0) libcurl/8.7.1 (SecureTransport) LibreSSL/3.3.6 zlib/1.2.12 nghttp2/1.67.1
Release-Date: 2024-03-27
```

## HTTP connectivity (status codes)
```
https://prometheus.prod.data.platform.smec.services/ -> 302
https://prometheus.prod.data.platform.smec.services/-/ready -> 200
https://prometheus.prod.data.platform.smec.services/api/v1/status/buildinfo -> 200
https://prometheus.prod.data.platform.smec.services/api/v1/labels -> 200
https://prometheus.prod.data.platform.smec.services/api/v1/label/__name__/values -> 200
```

## API samples (truncated)

### https://prometheus.prod.data.platform.smec.services/api/v1/status/buildinfo
```
{"status":"success","data":{"version":"2.44.0","revision":"1ac5131f698ebc60f13fe2727f89b115a41f6558","branch":"HEAD","buildUser":"root@739e8181c5db","buildDate":"20230514-06:18:11","goVersion":"go1.20.4"}}```
 asd sa ds 
### https://prometheus.prod.data.platform.smec.services/api/v1/labels
```
{"status":"success","data":["__name__","access_mode","action","active","address","alertmanager","alertname","alertstate","apiserver_id_hash","app","attacher","autosync_enabled","backend","binary","bios_date","bios_release","bios_vendor","bios_version","board_asset_tag","board_name","board_vendor","boot_id","bound","branch","broadcast","build","build_date","build_id","cache","call","call_status","cause","certificatesigningrequest","chassis_vendor","cidr","claim_namespace","class","clocksource","cluster_ip","code","code_path","collector","command","compiler","component","concurrency_policy","condition","config","configmap","constraint","container","container_id","container_runtime_version","container_state","container_type","controller","controller_class","controller_namespace","controller_p
```

### https://prometheus.prod.data.platform.smec.services/api/v1/label/__name__/values
```
{"status":"success","data":["ALERTS","ALERTS_FOR_STATE","access_evaluation_duration_bucket","access_evaluation_duration_count","access_evaluation_duration_sum","access_permissions_duration_bucket","access_permissions_duration_count","access_permissions_duration_sum","aggregator_discovery_aggregation_count_total","aggregator_unavailable_apiservice","aggregator_unavailable_apiservice_total","alertmanager_alerts","alertmanager_alerts_invalid_total","alertmanager_alerts_received_total","alertmanager_build_info","alertmanager_cluster_enabled","alertmanager_config_hash","alertmanager_config_last_reload_success_timestamp_seconds","alertmanager_config_last_reload_successful","alertmanager_dispatcher_aggregation_groups","alertmanager_dispatcher_alert_processing_duration_seconds_count","alertmanager
```

## promtool queries

### Instant: up
```
promtool query instant "https://prometheus.prod.data.platform.smec.services" 'up'
```
```
up{app="cert-manager", container="cert-manager", endpoint="9402", instance="10.48.16.130:9402", job="cert-manager", namespace="cert-manager", pod="cert-manager-79f9dff96d-f6sp8", service="cert-manager"} => 1 @[1768379567.72]
up{app="cert-manager", container="cert-manager", endpoint="9402", instance="10.48.18.53:9402", job="cert-manager", namespace="cert-manager", pod="cert-manager-79f9dff96d-qwrz8", service="cert-manager"} => 1 @[1768379567.72]
up{container="alertmanager", endpoint="http-web", instance="10.48.16.190:9093", job="kube-prometheus-stack-alertmanager", namespace="monitoring", pod="alertmanager-kube-prometheus-stack-alertmanager-0", service="kube-prometheus-stack-alertmanager"} => 1 @[1768379567.72]
up{container="argocd-application-controller", endpoint="metrics", instance="10.48.18.135:8082", job="argocd-metrics", namespace="argocd", pod="argocd-application-controller-0", service="argocd-metrics"} => 1 @[1768379567.72]
up{container="argocd-repo-server", endpoint="metrics", instance="10.48.18.32:8084", job="argocd-repo-server", namespace="argocd", pod="argocd-repo-server-7f7f584c5d-2jfgs", service="argocd-repo-server"} => 1 @[1768379567.72]
up{container="argocd-server", endpoint="metrics", instance="10.48.19.122:8083", job="argocd-server-metrics", namespace="argocd", pod="argocd-server-79fc4cb684-7tbwg", service="argocd-server-metrics"} => 1 @[1768379567.72]
up{container="controller", endpoint="metrics", instance="10.48.16.188:10254", job="ingress-nginx-private-controller-metrics", namespace="ingress-nginx-private", pod="ingress-nginx-private-controller-7fbfd748d4-d2fv9", service="ingress-nginx-private-controller-metrics"} => 1 @[1768379567.72]
up{container="controller", endpoint="metrics", instance="10.48.16.9:10254", job="ingress-nginx-private-controller-metrics", namespace="ingress-nginx-private", pod="ingress-nginx-private-controller-7fbfd748d4-7pb8s", service="ingress-nginx-private-controller-metrics"} => 1 @[1768379567.72]
up{container="controller", endpoint="metrics", instance="10.48.18.124:10254", job="ingress-nginx-private-controller-metrics", namespace="ingress-nginx-private", pod="ingress-nginx-private-controller-7fbfd748d4-9pvc2", service="ingress-nginx-private-controller-metrics"} => 1 @[1768379567.72]
up{container="controller", endpoint="metrics", instance="10.48.18.134:10254", job="ingress-nginx-public-controller-metrics", namespace="ingress-nginx-public", pod="ingress-nginx-public-controller-7f679d88f4-cp9v7", service="ingress-nginx-public-controller-metrics"} => 1 @[1768379567.72]
up{container="controller", endpoint="metrics", instance="10.48.18.31:10254", job="ingress-nginx-public-controller-metrics", namespace="ingress-nginx-public", pod="ingress-nginx-public-controller-7f679d88f4-6wcv8", service="ingress-nginx-public-controller-metrics"} => 1 @[1768379567.72]
up{container="controller", endpoint="metrics", instance="10.48.23.143:10254", job="ingress-nginx-public-controller-metrics", namespace="ingress-nginx-public", pod="ingress-nginx-public-controller-7f679d88f4-nhdx9", service="ingress-nginx-public-controller-metrics"} => 1 @[1768379567.72]
up{container="grafana", endpoint="http-web", instance="10.48.16.13:3000", job="kube-prometheus-stack-grafana", namespace="monitoring", pod="kube-prometheus-stack-grafana-675df5dc6-mcm2s", service="kube-prometheus-stack-grafana"} => 1 @[1768379567.72]
up{container="kube-prometheus-stack", endpoint="http", instance="10.48.19.123:8080", job="kube-prometheus-stack-operator", namespace="monitoring", pod="kube-prometheus-stack-operator-85c67879d6-b7964", service="kube-prometheus-stack-operator"} => 1 @[1768379567.72]
up{container="kube-state-metrics", endpoint="http", instance="10.48.18.30:8080", job="kube-state-metrics", namespace="monitoring", pod="kube-prometheus-stack-kube-state-metrics-ccfd46ddb-68lj2", service="kube-prometheus-stack-kube-state-metrics"} => 1 @[1768379567.72]
up{container="node-exporter", endpoint="http-metrics", instance="10.48.0.117:9100", job="node-exporter", namespace="monitoring", pod="kube-prometheus-stack-prometheus-node-exporter-86bmx", service="kube-prometheus-stack-prometheus-node-exporter"} => 1 @[1768379567.72]
up{container="node-exporter", endpoint="http-metrics", instance="10.48.0.120:9100", job="node-exporter", namespace="monitoring", pod="kube-prometheus-stack-prometheus-node-exporter-h4wmc", service="kube-prometheus-stack-prometheus-node-exporter"} => 1 @[1768379567.72]
up{container="node-exporter", endpoint="http-metrics", instance="10.48.0.122:9100", job="node-exporter", namespace="monitoring", pod="kube-prometheus-stack-prometheus-node-exporter-mdvht", service="kube-prometheus-stack-prometheus-node-exporter"} => 1 @[1768379567.72]
up{container="node-exporter", endpoint="http-metrics", instance="10.48.0.123:9100", job="node-exporter", namespace="monitoring", pod="kube-prometheus-stack-prometheus-node-exporter-8jq2w", service="kube-prometheus-stack-prometheus-node-exporter"} => 1 @[1768379567.72]
up{container="node-exporter", endpoint="http-metrics", instance="10.48.0.124:9100", job="node-exporter", namespace="monitoring", pod="kube-prometheus-stack-prometheus-node-exporter-xlcxg", service="kube-prometheus-stack-prometheus-node-exporter"} => 1 @[1768379567.72]
up{container="node-exporter", endpoint="http-metrics", instance="10.48.0.125:9100", job="node-exporter", namespace="monitoring", pod="kube-prometheus-stack-prometheus-node-exporter-pdj64", service="kube-prometheus-stack-prometheus-node-exporter"} => 1 @[1768379567.72]
up{container="node-exporter", endpoint="http-metrics", instance="10.48.0.127:9100", job="node-exporter", namespace="monitoring", pod="kube-prometheus-stack-prometheus-node-exporter-4h29q", service="kube-prometheus-stack-prometheus-node-exporter"} => 1 @[1768379567.72]
up{container="node-exporter", endpoint="http-metrics", instance="10.48.0.14:9100", job="node-exporter", namespace="monitoring", pod="kube-prometheus-stack-prometheus-node-exporter-927hc", service="kube-prometheus-stack-prometheus-node-exporter"} => 1 @[1768379567.72]
up{container="node-exporter", endpoint="http-metrics", instance="10.48.0.15:9100", job="node-exporter", namespace="monitoring", pod="kube-prometheus-stack-prometheus-node-exporter-n2sgg", service="kube-prometheus-stack-prometheus-node-exporter"} => 1 @[1768379567.72]
up{container="node-exporter", endpoint="http-metrics", instance="10.48.0.20:9100", job="node-exporter", namespace="monitoring", pod="kube-prometheus-stack-prometheus-node-exporter-nnn8q", service="kube-prometheus-stack-prometheus-node-exporter"} => 1 @[1768379567.72]
up{container="node-exporter", endpoint="http-metrics", instance="10.48.0.23:9100", job="node-exporter", namespace="monitoring", pod="kube-prometheus-stack-prometheus-node-exporter-sdglt", service="kube-prometheus-stack-prometheus-node-exporter"} => 1 @[1768379567.72]
up{container="node-exporter", endpoint="http-metrics", instance="10.48.0.27:9100", job="node-exporter", namespace="monitoring", pod="kube-prometheus-stack-prometheus-node-exporter-r9vk7", service="kube-prometheus-stack-prometheus-node-exporter"} => 1 @[1768379567.72]
up{container="node-exporter", endpoint="http-metrics", instance="10.48.0.28:9100", job="node-exporter", namespace="monitoring", pod="kube-prometheus-stack-prometheus-node-exporter-6qfr2", service="kube-prometheus-stack-prometheus-node-exporter"} => 1 @[1768379567.72]
up{container="node-exporter", endpoint="http-metrics", instance="10.48.0.29:9100", job="node-exporter", namespace="monitoring", pod="kube-prometheus-stack-prometheus-node-exporter-mq7ct", service="kube-prometheus-stack-prometheus-node-exporter"} => 1 @[1768379567.72]
up{container="node-exporter", endpoint="http-metrics", instance="10.48.0.31:9100", job="node-exporter", namespace="monitoring", pod="kube-prometheus-stack-prometheus-node-exporter-7fvdq", service="kube-prometheus-stack-prometheus-node-exporter"} => 1 @[1768379567.72]
up{container="node-exporter", endpoint="http-metrics", instance="10.48.0.33:9100", job="node-exporter", namespace="monitoring", pod="kube-prometheus-stack-prometheus-node-exporter-9rrzn", service="kube-prometheus-stack-prometheus-node-exporter"} => 1 @[1768379567.72]
up{container="node-exporter", endpoint="http-metrics", instance="10.48.0.34:9100", job="node-exporter", namespace="monitoring", pod="kube-prometheus-stack-prometheus-node-exporter-4k5rq", service="kube-prometheus-stack-prometheus-node-exporter"} => 1 @[1768379567.72]
up{container="node-exporter", endpoint="http-metrics", instance="10.48.0.36:9100", job="node-exporter", namespace="monitoring", pod="kube-prometheus-stack-prometheus-node-exporter-8c9vn", service="kube-prometheus-stack-prometheus-node-exporter"} => 1 @[1768379567.72]
up{container="node-exporter", endpoint="http-metrics", instance="10.48.0.46:9100", job="node-exporter", namespace="monitoring", pod="kube-prometheus-stack-prometheus-node-exporter-mxvgk", service="kube-prometheus-stack-prometheus-node-exporter"} => 1 @[1768379567.72]
up{container="node-exporter", endpoint="http-metrics", instance="10.48.0.49:9100", job="node-exporter", namespace="monitoring", pod="kube-prometheus-stack-prometheus-node-exporter-997xv", service="kube-prometheus-stack-prometheus-node-exporter"} => 1 @[1768379567.72]
up{container="node-exporter", endpoint="http-metrics", instance="10.48.0.51:9100", job="node-exporter", namespace="monitoring", pod="kube-prometheus-stack-prometheus-node-exporter-2fvbx", service="kube-prometheus-stack-prometheus-node-exporter"} => 1 @[1768379567.72]
up{container="node-exporter", endpoint="http-metrics", instance="10.48.0.53:9100", job="node-exporter", namespace="monitoring", pod="kube-prometheus-stack-prometheus-node-exporter-88h76", service="kube-prometheus-stack-prometheus-node-exporter"} => 1 @[1768379567.72]
up{container="node-exporter", endpoint="http-metrics", instance="10.48.0.55:9100", job="node-exporter", namespace="monitoring", pod="kube-prometheus-stack-prometheus-node-exporter-9mscv", service="kube-prometheus-stack-prometheus-node-exporter"} => 1 @[1768379567.72]
up{container="node-exporter", endpoint="http-metrics", instance="10.48.0.82:9100", job="node-exporter", namespace="monitoring", pod="kube-prometheus-stack-prometheus-node-exporter-6r2km", service="kube-prometheus-stack-prometheus-node-exporter"} => 1 @[1768379567.72]
up{container="node-exporter", endpoint="http-metrics", instance="10.48.0.8:9100", job="node-exporter", namespace="monitoring", pod="kube-prometheus-stack-prometheus-node-exporter-78ck8", service="kube-prometheus-stack-prometheus-node-exporter"} => 1 @[1768379567.72]
```

### Instant: count(up)
```
promtool query instant "https://prometheus.prod.data.platform.smec.services" 'count(up)'
```
```
{} => 137 @[1768379567.96]
```

## Notes / Next probes
- If any endpoint returns 401/403, we need to add auth (cookie/header) for both curl and promtool.
- Next useful API calls: https://prometheus.prod.data.platform.smec.services/api/v1/targets , https://prometheus.prod.data.platform.smec.services/api/v1/rules .

---

## promwrap CLI smoke test
Date: 2026-01-14

Commands executed (via `uv run`):
- `promwrap --url "$PROM_URL" ping` → `ok`
- `promwrap --url "$PROM_URL" buildinfo --output json` → success (Prometheus `2.44.0`)
- `promwrap --url "$PROM_URL" query 'count(up)' --output json` → success (returned `73`)
- `promwrap --url "$PROM_URL" metrics --match 'argocd' --limit 10` → returned 10 metric names

CLI UX finding:
- Fixed argument parsing so “global” flags like `--output/--url` work **both before and after** the subcommand (e.g. `promwrap ping --url ... --output json`).

---

## promwrap DSPy tool logging smoke test (`promwraptoollogging`)
Date: 2026-01-14

Run:
- `PROM_URL="$PROM_URL" uv run promwraptoollogging`

Observed behavior:
- DSPy selected model access prefix: `vertex_ai`.
- Tool calls executed successfully and were logged by `ToolCallCallback`:
  - `prom_metrics(match_regex="argocd", limit=10)` → returned 10 metric names (`argocd_*`).
  - `prom_query(promql="count(up)")` → success; returned value `77`.
- Process exited with code `0`.

Note:
- The `count(up)` value differs from the earlier `promwrap` CLI run because it is sampled at a different point in time.
