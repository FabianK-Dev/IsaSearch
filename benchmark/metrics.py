import math

top_k = 10

def is_correct_target(result, target_identifier):
    for identifier in target_identifier:
        print(result["id"])
        if result["doc"][identifier] == target_identifier[identifier]:
            print("YES :)")
            return True

    print("NO :(")
    return False

# For a given query, is the target_identifier among the top-k search results? => TRUE / FALSE
def top_k_accuracy(results, target_id):
    for i, result in enumerate(results):
        if i >= top_k: # i starts at 0 => if i == top_k we can gurantee that the result was not within the first k results
            return False

        if is_correct_target(result, target_id):
            return True
    
    return False

# Calculates a relevance scale of the retrieved documents
# The reelvance value is reduced logarithmically depending on the result position
def discounted_cumulative_gain(results, target_identifier):
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
