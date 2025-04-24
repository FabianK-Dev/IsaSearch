#!/bin/bash

config="config.json"
isabelle_binary_file=$(jq -r '.isabelle_binary_file' "$config")

echo "Install Isabelle and the AFP"
python3 -m src.installation

echo "Install Isabelle components"
echo "Isabelle binary is located at $isabelle_binary_file"

$isabelle_binary_file components -a
$isabelle_binary_file find_facts_index

python3 -m src.app
