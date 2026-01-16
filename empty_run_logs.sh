#!/bin/bash

truncate -s 0 src/optimize_agent/run_logs/metrics.csv
truncate -s 0 src/optimize_agent/run_logs/runs.csv

rm src/optimize_agent/run_logs/*.log
rm src/optimize_agent/run_logs/*.json
