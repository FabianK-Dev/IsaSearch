#!/bin/bash

while true; do
  python -m benchmark.benchmark
  echo "Process exited with status $?. Restarting after delay..."
  sleep 300
done
