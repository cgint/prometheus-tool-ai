# Prometheus Tools Deep Detail

This document provides a detailed explanation of the Prometheus tools available in `src/tools/prom.py`. These tools are designed to allow an AI agent or a user to discover, explore, and query data from a Prometheus server.

## 1. `prom_buildinfo`

### Purpose
Retrieves the build and version information of the Prometheus server.

### Detailed Description
This tool calls the `/api/v1/status/buildinfo` endpoint. it returns metadata about the Prometheus binary itself, including:
- `version`: The version string (e.g., "2.45.0").
- `revision`: The git commit SHA it was built from.
- `buildDate`: When the binary was built.
- `goVersion`: The Go version used for the build.

### AI Usage Guidance
- **Discovery Phase:** Use this tool at the start of a session if you need to know the capabilities of the Prometheus server (certain features might only be available in newer versions).
- **Troubleshooting:** Use it to confirm the environment if queries are behaving unexpectedly.

---

## 2. `prom_metrics`

### Purpose
Lists available metric names in the Prometheus instance.

### Detailed Description
Calls the `/api/v1/label/__name__/values` endpoint (effectively) or `/api/v1/metadata`. It provides a list of all strings that represent valid metric names (e.g., `up`, `http_requests_total`).

### Parameters
- `match_regex` (Optional): A regular expression to filter the metric names. This is executed client-side in the tool.
- `limit` (Default: 50): Limits the number of results returned to prevent overwhelming the agent with thousands of metrics.

### AI Usage Guidance
- **Exploration:** This is the primary tool for finding *what* can be measured. If you are asked about "latency", you might call `prom_metrics(match_regex='.*latency.*')`.
- **Constraint:** Always use a regex if you have a hint of what you're looking for, as Prometheus instances often have thousands of metrics.

---

## 3. `prom_labels`

### Purpose
Lists all unique label names across all time series.

### Detailed Description
Calls the `/api/v1/labels` endpoint. Labels are the dimensions of Prometheus metrics (e.g., `method`, `status`, `instance`, `job`).

### Parameters
- `limit` (Default: 50): Limits the number of label names returned.

### AI Usage Guidance
- **Schema Discovery:** Use this to understand what dimensions are available for filtering in your PromQL queries.
- **Query Refinement:** If a query returns too much data, check `prom_labels` to see if you can filter by a specific dimension like `namespace` or `service`.

---

## 4. `prom_label_values`

### Purpose
Lists all unique values for a specific label name.

### Detailed Description
Calls the `/api/v1/label/<label_name>/values` endpoint. For a given label like `job`, it might return `['prometheus', 'node-exporter', 'api-server']`.

### Parameters
- `label`: The name of the label to fetch values for (Required).
- `match_regex` (Optional): A regex to filter the returned values.
- `limit` (Default: 50): Limits the number of values returned.

### AI Usage Guidance
- **Query Parameterization:** Before writing a PromQL query with a filter like `{job="my-service"}`, use this tool to ensure "my-service" is a valid value for the `job` label.
- **Drill-down:** If you know a metric has a `status` label, use this to see if the values are `200`, `404`, `500`, etc.

---

## 5. `prom_query`

### Purpose
Performs an "instant" PromQL query at a single point in time.

### Detailed Description
Calls the `/api/v1/query` endpoint. It evaluates a PromQL expression and returns the result as it exists at the specified `time`.

### Parameters
- `promql`: The PromQL expression to evaluate (e.g., `rate(http_requests_total[5m])`).
- `time` (Default: "now"): The evaluation time. Can be an RFC3339 timestamp, "now", or a relative offset like "1h" (meaning 1 hour ago).

### AI Usage Guidance
- **Current Status:** Use this for "What is the current value?" or "Is the system healthy right now?".
- **Aggregations:** Use it for queries that return a single value or a vector of current values across different labels.
- **Example:** `prom_query(promql='sum(up)')` tells you how many targets are currently up.

---

## 6. `prom_range`

### Purpose
Performs a PromQL query over a range of time (time-series data).

### Detailed Description
Calls the `/api/v1/query_range` endpoint. It returns a set of data points for the expression over the interval `[start, end]` at every `step` interval.

### Parameters
- `promql`: The PromQL expression to evaluate.
- `start`: The start of the time range (e.g., "1h" for one hour ago).
- `end` (Default: "now"): The end of the time range.
- `step` (Default: "30s"): The query resolution step (e.g., "15s", "1m", "5m").

### AI Usage Guidance
- **Trend Analysis:** Use this for "Show me the CPU usage over the last hour" or "Has the error rate increased since this morning?".
- **Visualizing/Graphing:** This is the tool to use if you need to provide data for a chart or identify patterns over time.
- **Performance:** Be mindful of the `step` and time range. A very small step over a large range can return a massive amount of data.
