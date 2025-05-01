docker run -d -p 8983:8983 -v /home/fabian/.isabelle/Isabelle2025/find_facts/solr/local:/opt/solr/server/solr/local solr:latest solr-precreate local /opt/solr/server/solr/local
