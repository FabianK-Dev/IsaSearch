import math

top_k = 10

# For a given query, is the target among the top-k search results? => TRUE / FALSE
def top_k_accuracy(results, target_id):
    for result in results:
        if result["id"] == target_id:
            return True
    
    return False

# Calculates a relevance scale of the retrieved documents
# The reelvance value is reduced logarithmically depending on the result position
def discounted_cumulative_gain(results, target_id):
    for i in range(len(results)):
        if results["id"] == target_id:
            return 1 / math.log2(i + 2) # the first loop iteration starts at 0, not 1, thus we have to add 2 instead of 1

    return 0 # If the relevant target document (identified by target_id) is not in the search results
