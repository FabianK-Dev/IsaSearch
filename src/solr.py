import pysolr

def connect_solr(config):
    print(f"Connect to Solr at " + config["solr_core_url"] + "...")
    solr = pysolr.Solr(config["solr_core_url"], always_commit=True, timeout=10)

    print("Ping Solr for health check...")
    solr.ping() # Health check
