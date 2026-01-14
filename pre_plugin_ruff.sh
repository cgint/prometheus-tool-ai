#!/bin/bash

# Detect package manager and set run command
if [ -f "uv.lock" ]; then
    echo "Detected uv.lock ... running in uv-managed mode"
    RUN_CMD="uv run"
    LIST_CMD="uv pip list"
    ADD_CMD="uv add --dev"
else
    echo "Error: uv.lock not found. Please ensure project uses UV for dependency management"
    exit 1
fi

set -euo pipefail

# Never check pip for new version while running this script
export PIP_DISABLE_PIP_VERSION_CHECK=1

# Check if ruff is installed globally
if ! ($LIST_CMD | grep "ruff" > /dev/null); then
    echo
    echo "Installing 'ruff' in current project"
    echo
    $ADD_CMD "ruff"
fi

PLUGIN_NAME="Ruff"
echo
echo "Running Plugin $PLUGIN_NAME..."
$RUN_CMD ruff check --fix
ruff_status=$? # Capture the exit status

# Optional: Add logging based on status
if [ $ruff_status -ne 0 ]; then
    echo "Plugin $PLUGIN_NAME failed with status $ruff_status" >&2
fi

exit $ruff_status # Exit with the actual status of the ruff command 