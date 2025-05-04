import math

def is_correct_target(result, target_identifier):
    for identifier in target_identifier:
        if not identifier in result["doc"]:
            print("Warning: Identifier '" + identifier + "' does not exist in the document dictionary of result with ID " + result["id"] + ". Cannot verify if this is the target document.")
            continue

        print("OURS:", result["doc"][identifier])
        print("GOLD:", target_identifier[identifier])

        if result["doc"][identifier] == target_identifier[identifier]:
            print("YES :)")
            return True

    print("NO :(")
    return False

# For a given query, is the target_identifier among the top-k search results? => 1 (yes) / 0 (false)
top_k = 10
def top_k_accuracy(results, target_id):
    for i, result in enumerate(results):
        if i >= top_k: # i starts at 0 => if i == top_k we can gurantee that the result was not within the first k results
            return 0

        if is_correct_target(result, target_id):
            return 1
    
    return False

# Calculates a relevance scale of the retrieved documents
# The reelvance value is reduced logarithmically depending on the result position
def normalized_discounted_cumulative_gain(results, target_identifier):
    for i in range(len( results )):
        if is_correct_target(results[i], target_identifier):
            return 1 / math.log2(i + 2) # the first loop iteration starts at 0, not 1, thus we have to add 2 instead of 1

    return 0 # If the relevant target document (identified by target_id) is not in the search results

# reciprocal_rank = (1 / rank) where rank_i is the rank of the first relevant document
def reciprocal_rank(results, target_identifier): 
    for i, result in enumerate(results):
        if is_correct_target(result, target_identifier):
            return 1 / (i + 1)

    return 0

def calculate_mean_metrics(benchmark_results):
    metrics = {}

    for target_id in benchmark_results:
        for query_type in benchmark_results[target_id]:
            if query_type == "skipped" and benchmark_results[target_id]["skipped"]:
                print("Skipping '" + target_id + "' in metrics mean calculation because it is marked as \"skipped\" = True")
                break

            for metric in benchmark_results[target_id][query_type]:
                metric_value = benchmark_results[target_id][query_type][metric]
                if metric not in metrics:
                    metrics[metric] = { "total": 0, "sample_size": 0 }
                
                metrics[metric]["total"] += metric_value
                metrics[metric]["sample_size"] += 1

    # Calculate the average
    for metric in metrics:
        metrics[metric]["average"] = metrics[metric]["total"] / metrics[metric]["sample_size"]
        del metrics[metric]["total"]

    print(metrics)
