"""
solr.py: This file connects to Solr and retrieves documents by their IDs.
"""

import pysolr


# Connects to a running Solr database which is reachable at config["solr_core_url"].
# Afterwards a health check is done to ensure Solr is running correctly.
def connect_solr(config):
    print("Connect to Solr at " + config["solr_core_url"] + "...")
    solr = pysolr.Solr(config["solr_core_url"], always_commit=True, timeout=10)

    print("Ping Solr for health check...")
    solr.ping()

    return solr


# Given a list of Solr document IDs, return a list of all documents identified by the IDs.
def docs_by_ids(solr, ids):
    id_strings = []

    for _id in ids:
        id_string = "id:" + _id
        id_strings.append(id_string)

    id_query = " OR ".join(id_strings)
    results = solr.search(id_query, start=0, rows=100)

    return results
