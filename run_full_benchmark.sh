#!/bin/bash

echo "WARNING: Running the full benchmark will delete .cache/document_index.json and will temporarily update the config.json file. At the end of the run, config.json will be reset using 'git checkout -- config.json'. Please type confirm and hit enter to continue..."
read confirm

if [ "$confirm" != "confirm" ];
then
  echo "Not confirmed."
  exit
fi

# Don't add metadata to embeddings, refine the query but don't append the original user query
rm .cache/document_index.json
jq '.add_metadata = false' config.json > tmp && mv tmp config.json
jq '.add_user_query = false' config.json > tmp && mv tmp config.json
jq '.benchmark_search_refine = true' config.json > tmp && mv tmp config.json
python -m benchmark.benchmark

# Don't add metadata to embeddings, but only use the original user query without query refinement
rm .cache/document_index.json
jq '.add_metadata = false' config.json > tmp && mv tmp config.json
jq '.add_user_query = false' config.json > tmp && mv tmp config.json
jq '.benchmark_search_refine = false' config.json > tmp && mv tmp config.json
python -m benchmark.benchmark

# Don't add metadata to embeddings, use query refinement and add the original user query
rm .cache/document_index.json
jq '.add_metadata = false' config.json > tmp && mv tmp config.json
jq '.add_user_query = true' config.json > tmp && mv tmp config.json
jq '.benchmark_search_refine = true' config.json > tmp && mv tmp config.json
python -m benchmark.benchmark

# Add metadata to embeddings, refine the query but don't append the original user query
rm .cache/document_index.json
jq '.add_metadata = true' config.json > tmp && mv tmp config.json
jq '.add_user_query = false' config.json > tmp && mv tmp config.json
jq '.benchmark_search_refine = true' config.json > tmp && mv tmp config.json
python -m benchmark.benchmark

# Add metadata to embeddings, but only use the original user query without query refinement
rm .cache/document_index.json
jq '.add_metadata = true' config.json > tmp && mv tmp config.json
jq '.add_user_query = false' config.json > tmp && mv tmp config.json
jq '.benchmark_search_refine = false' config.json > tmp && mv tmp config.json
python -m benchmark.benchmark

# Add metadata to embeddings, use query refinement and add the original user query
rm .cache/document_index.json
jq '.add_metadata = true' config.json > tmp && mv tmp config.json
jq '.add_user_query = true' config.json > tmp && mv tmp config.json
jq '.benchmark_search_refine = true' config.json > tmp && mv tmp config.json
python -m benchmark.benchmark

# Reset the config.json
git checkout -- config.json
