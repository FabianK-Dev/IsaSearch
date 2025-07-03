#!/bin/bash

# Don't add metadata to embeddings, refine the query but don't append the original user query
jq '.add_metadata = false' config.json > tmp && mv tmp config.json
jq '.add_user_query = false' config.json > tmp && mv tmp config.json
jq '.benchmark_search_refine = true' config.json > tmp && mv tmp config.json
python -m benchmark.benchmark

# Don't add metadata to embeddings, but only use the original user query without query refinement
jq '.add_metadata = false' config.json > tmp && mv tmp config.json
jq '.add_user_query = false' config.json > tmp && mv tmp config.json
jq '.benchmark_search_refine = false' config.json > tmp && mv tmp config.json
python -m benchmark.benchmark

# Don't add metadata to embeddings, use query refinement and add the original user query
jq '.add_metadata = false' config.json > tmp && mv tmp config.json
jq '.add_user_query = true' config.json > tmp && mv tmp config.json
jq '.benchmark_search_refine = true' config.json > tmp && mv tmp config.json
python -m benchmark.benchmark

# Add metadata to embeddings, refine the query but don't append the original user query
jq '.add_metadata = true' config.json > tmp && mv tmp config.json
jq '.add_user_query = false' config.json > tmp && mv tmp config.json
jq '.benchmark_search_refine = true' config.json > tmp && mv tmp config.json
python -m benchmark.benchmark

# Add metadata to embeddings, but only use the original user query without query refinement
jq '.add_metadata = true' config.json > tmp && mv tmp config.json
jq '.add_user_query = false' config.json > tmp && mv tmp config.json
jq '.benchmark_search_refine = false' config.json > tmp && mv tmp config.json
python -m benchmark.benchmark

# Add metadata to embeddings, use query refinement and add the original user query
jq '.add_metadata = true' config.json > tmp && mv tmp config.json
jq '.add_user_query = true' config.json > tmp && mv tmp config.json
jq '.benchmark_search_refine = true' config.json > tmp && mv tmp config.json
python -m benchmark.benchmark

# Reset the config.json
git checkout -- config.json
