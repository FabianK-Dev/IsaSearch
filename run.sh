#!/bin/bash

config="config.json"
isabelle_binary_file=$(jq -r '.isabelle_binary_file' "$config")
afp_folder=$(jq -r '.afp_folder' "$config")

echo "Install Isabelle and the AFP"
python3 -m src.installation

echo "Install Isabelle components"
echo "Isabelle binary is located at $isabelle_binary_file"

$isabelle_binary_file components -a
$isabelle_binary_file find_facts_index -v -A "$afp_folder/" $(cat "$afp_folder/thys/ROOTS")

python3 -m src.app
