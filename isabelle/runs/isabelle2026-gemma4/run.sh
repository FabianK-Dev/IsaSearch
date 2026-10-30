#!/usr/bin/env bash
# Build the plain and the metadata index of Isabelle2026 + AFP 2026 (see README.md).
# Requires isabelle on PATH and ISASEARCH_API_KEY for the model servers.
set -euo pipefail
cd "$(dirname "$0")"
: "${ISASEARCH_API_KEY:?Set ISASEARCH_API_KEY for the model servers}"
logs="$(isabelle getenv -b ISASEARCH_HOME_USER)/logs"
mkdir -p "$logs"
stamp="$(date +%Y%m%d-%H%M%S)"
isabelle isasearch_index -c plain.json -i plain 2>&1 | tee "$logs/plain-$stamp.log"
# The sessions are built and indexed by now: -n reuses them and the FindFacts index.
isabelle isasearch_index -c metadata.json -i metadata -n 2>&1 | tee "$logs/metadata-$stamp.log"
