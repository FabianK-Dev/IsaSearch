import math

def is_correct_target(result_doc, target_identifier):
    for identifier in target_identifier:
        for identifier_key in identifier:
            if not identifier_key in result_doc:
                # print("Warning: Identifier key '" + identifier_key + "' does not exist in the document dictionary of result with ID " + result["id"] + ". Cannot verify if this is the target document.")
                continue

            if result_doc[identifier_key] == identifier[identifier_key]:
                return True

    return False

# For a given query, is the target_identifier among the top-k search results? => 1 (yes) / 0 (false)
top_k = 10
def top_k_accuracy(results, target_id):
    for i, result in enumerate(results):
        if i >= top_k: # i starts at 0 => if i == top_k we can gurantee that the result was not within the first k results
            return 0

        if is_correct_target(result, target_id):
            return 1
    
    return 0

# Calculates a relevance scale of the retrieved documents
# The reelvance value is reduced logarithmically depending on the result position
def normalized_discounted_cumulative_gain(results, target_identifier):
    dcg = 0

    for i, result in enumerate(results):
        if is_correct_target(result, target_identifier):
            dcg += 1 / math.log2(i + 2) # the first loop iteration starts at 0, not 1, thus we have to add 2 instead of 1

    idcg = 0
    for i in range(len(target_identifier)):
        idcg += 1 / math.log2(i + 2)
    
    if idcg > 0:
        return dcg / idcg
    else:
        return 0

# reciprocal_rank = (1 / rank) where rank_i is the rank of the first relevant document
def reciprocal_rank(results, target_identifier): 
    for i, result in enumerate(results):
        if is_correct_target(result, target_identifier):
            return 1 / (i + 1)

    return 0

def rank(results, target_identifier):
    for i, result in enumerate(results):
        if is_correct_target(result, target_identifier):
            return i + 1

    return len(results)

def calculate_mean_metrics(benchmark_results):
    metrics = {}

    for target_id in benchmark_results:
        is_skipped = "skipped" in benchmark_results[target_id]["metadata"] and benchmark_results[target_id]["metadata"]["skipped"]
        if is_skipped:
            print("Skipping '" + target_id + "' in metrics mean calculation because it is marked as \"skipped\" = True")
            continue

        for query_type in benchmark_results[target_id]["queries"]:
            for metric in benchmark_results[target_id]["queries"][query_type]["metrics"]:
                metric_value = benchmark_results[target_id]["queries"][query_type]["metrics"][metric]
                if metric not in metrics:
                    metrics[metric] = { "total": 0, "sample_size": 0 }
                
                metrics[metric]["total"] += metric_value
                metrics[metric]["sample_size"] += 1

    # Calculate the average
    for metric in metrics:
        metrics[metric]["average"] = metrics[metric]["total"] / metrics[metric]["sample_size"]
        del metrics[metric]["total"]

    return metrics
