import pysolr

def connect_solr(config):
    print(f"Connect to Solr at " + config["solr_core_url"] + "...")
    solr = pysolr.Solr(config["solr_core_url"], always_commit=True, timeout=10)

    print("Ping Solr for health check...")
    solr.ping() # Health check

    return solr

def docs_by_ids(solr, ids):
    id_strings = []

    for _id in ids:
        id_string = "id:" + _id
        id_strings.append(id_string)

    id_query = " OR ".join(id_strings)
    results = solr.search(id_query, start=0, rows=100)

    return results
