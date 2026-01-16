#!/bin/bash

echo -n "" > src/optimize_agent/run_logs/metrics.csv
echo -n "" > src/optimize_agent/run_logs/runs.csv

rm src/optimize_agent/run_logs/*.log
rm src/optimize_agent/run_logs/*.json
