# Ideal expected output for the promwrap tool logging demo

File: `promwrap_tool_logging.py`

## Ideal output

The most important part here is that
- The Tool `python_repl` correctly usese Inputs: {'code': "len(prom_query_0['data']['result'])} as the tool gets information wired from previous tool calls.
- The AI knows to use the prom_query_0 variable from the previous tool call.


```
 > now run it

 ● Running the promwraptoollogging entrypoint to confirm the python_repl can reference prom_query_0 now.

 ✓ Run the promwrap tool logging demo
   $ cd /Users/christian.gintenreiter/dev/prometheus-tool && uv run promwraptoollogging
   ╭─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
   │ Using model access prefix: vertex_ai                                                                                                                                        │
   │                                                                                                                                                                             │
   │ Question:                                                                                                                                                                   │
   │  -> List kube service info metrics for namespace argocd. Also calculate the count of entries as python code                                                                 │
   │                                                                                                                                                                             │
   │                                                                                                                                                                             │
   │ ============================================================                                                                                                                │
   │ 📊 Tool Usage Summary                                                                                                                                                       │
   │ ============================================================                                                                                                                │
   │                                                                                                                                                                             │
   │ 1. Tool: prom_metrics                                                                                                                                                       │
   │    Inputs: {}                                                                                                                                                               │
   │    Output: ['ALERTS', 'ALERTS_FOR_STATE', 'access_evaluation_duration_bucket', 'access_evaluation_duration_count', 'access_evaluation_duration_sum',                        │
   │ 'access_permissions_duration_bucket', 'access_permissions_duration_count', 'access_permissions_duration_sum', 'aggregator_discovery_aggregation_count_total',               │
   │ 'aggregator_unavailable_apiservice', 'aggregator_unavailable_apiservice_total', 'alertmanager_alerts', 'alertmanager_alerts_invalid_total',                                 │
   │ 'alertmanager_alerts_received_total', 'alertmanager_build_info', 'alertmanager_cluster_enabled', 'alertmanager_config_hash',                                                │
   │ 'alertmanager_config_last_reload_success_timestamp_seconds', 'alertmanager_config_last_reload_successful', 'alertmanager_dispatcher_aggregation_groups',                    │
   │ 'alertmanager_dispatcher_alert_processing_duration_seconds_count', 'alertmanager_dispatcher_alert_processing_duration_seconds_sum',                                         │
   │ 'alertmanager_http_concurrency_limit_exceeded_total', 'alertmanager_http_request_duration_seconds_bucket', 'alertmanager_http_request_duration_<output too long - dropped   │
   │ 1156 characters from the end>                                                                                                                                               │
   │    Status: completed                                                                                                                                                        │
   │                                                                                                                                                                             │
   │ 2. Tool: prom_metrics                                                                                                                                                       │
   │    Inputs: {'match_regex': 'kube_service_info'}                                                                                                                             │
   │    Output: ['kube_service_info']                                                                                                                                            │
   │    Status: completed                                                                                                                                                        │
   │                                                                                                                                                                             │
   │ 3. Tool: prom_query                                                                                                                                                         │
   │    Inputs: {'promql': 'kube_service_info{namespace="argocd"}'}                                                                                                              │
   │    Output: {'status': 'success', 'data': {'resultType': 'vector', 'result': [{'metric': {'__name__': 'kube_service_info', 'cluster_ip': '10.48.4.116', 'container':         │
   │ 'kube-state-metrics', 'endpoint': 'http', 'instance': '10.48.18.30:8080', 'job': 'kube-state-metrics', 'namespace': 'argocd', 'pod':                                        │
   │ 'kube-prometheus-stack-kube-state-metrics-ccfd46ddb-68lj2', 'service': 'argocd-server', 'uid': 'f07a70af-332f-4302-b272-e9b141d4f62c'}, 'value': [1768402459.963, '1']},    │
   │ {'metric': {'__name__': 'kube_service_info', 'cluster_ip': '10.48.4.215', 'container': 'kube-state-metrics', 'endpoint': 'http', 'instance': '10.48.18.30:8080', 'job':     │
   │ 'kube-state-metrics', 'namespace': 'argocd', 'pod': 'kube-prometheus-stack-kube-state-metrics-ccfd46ddb-68lj2', 'service': 'argocd-server-metrics', 'uid':                  │
   │ 'be687422-9a7a-4599-89d9-b4d96460995b'}, 'value': [1768402459.963, '1']}, {'metric': {'__name__': 'kube_service_info', 'cluster_ip': '10.48.4.24', 'container':             │
   │ 'kube-state-metrics', 'endpoint': 'http', 'instance<output too long - dropped 2249 characters from the end>                                                                 │
   │    Status: completed                                                                                                                                                        │
   │                                                                                                                                                                             │
   │ 4. Tool: python_repl                                                                                                                                                        │
   │    Inputs: {'code': "len(prom_query_0['data']['result'])"}                                                                                                                  │
   │    Output: 8                                                                                                                                                                │
   │    Status: completed                                                                                                                                                        │
   │                                                                                                                                                                             │
   │ 5. Tool: finish                                                                                                                                                             │
   │    Inputs: {}                                                                                                                                                               │
   │    Output: Completed.                                                                                                                                                       │
   │    Status: completed                                                                                                                                                        │
   │ ============================================================                                                                                                                │
   │                                                                                                                                                                             │
   │                                                                                                                                                                             │
   │ Answer:                                                                                                                                                                     │
   │  -> The kube service info metrics for the namespace 'argocd' are:                                                                                                           │
   │ - service: argocd-server, cluster_ip: 10.48.4.116                                                                                                                           │
   │ - service: argocd-server-metrics, cluster_ip: 10.48.4.215                                                                                                                   │
   │ - service: argocd-applicationset-controller, cluster_ip: 10.48.4.24                                                                                                         │
   │ - service: argocd-notifications-controller-metrics, cluster_ip: 10.48.4.27                                                                                                  │
   │ - service: argocd-metrics, cluster_ip: 10.48.5.145                                                                                                                          │
   │ - service: argocd-dex-server, cluster_ip: 10.48.5.166                                                                                                                       │
   │ - service: argocd-repo-server, cluster_ip: 10.48.5.190                                                                                                                      │
   │ - service: argocd-redis, cluster_ip: 10.48.5.84                                                                                                                             │
   │                                                                                                                                                                             │
   │ There are 8 entries.                                                                                                                                                        │
   │ <exited with exit code 0>                                                                                                                                                   │
   ╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯

 ● It works now.

     - Tool #4 (python_repl) successfully evaluated: len(prom_query_0['data']['result']) → 8
     - Full run completed with exit code 0 and returned the 8 kube_service_info entries for namespace="argocd".
```