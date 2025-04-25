#!/bin/bash
# DEPRECATED => needs rework

config="config.json"
isabelle_binary_file=$(jq -r '.isabelle_binary_file' "$config")
isabelle_version=$(jq -r '.isabelle_version' "$config")
afp_folder=$(jq -r '.afp_folder' "$config")

echo "Install Isabelle and the AFP"
python3 -m src.installation

echo "Install Isabelle components"
echo "Isabelle binary is located at $isabelle_binary_file"
$isabelle_binary_file components -a
$isabelle_binary_file find_facts_index -v -A "$afp_folder/" CYK #$(cat "$afp_folder/thys/ROOTS")

echo "Start docker container if it already exists but is not running."
docker start isabelle-solr || \
    docker run -d --name isabelle-solr \
        -p 8983:8983 \
        -v /home/fabian/.isabelle/Isabelle2025/find_facts/solr/local:/opt/solr/server/solr/local \
        solr:latest \
        solr-precreate local /opt/solr/server/solr/local

python3 -m src.app
