FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    wget openjdk-17-jre-headless \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN wget https://www.apache.org/dyn/closer.lua/solr/solr/9.8.1/solr-9.8.1.tgz?action=download -O solr-9.8.1.tgz \
    && tar -xzf solr-9.8.1.tgz \
    && mv solr-9.8.1 /opt/solr \
    && rm solr-9.8.1.tgz

RUN mkdir -p /opt/solr/server/solr/local
ENV SOLR_HOME=/opt/solr
ENV PATH="$SOLR_HOME/bin:$PATH"

COPY . /app/
RUN tar -xf assets/artifacts.tar.gz assets/cache.tar.gz assets/chroma_storages.tar.gz assets/find_facts.tar.gz 

CMD ["solr", "start", "--force", "-p", "8983", "-s", "/opt/solr/server/solr/local"]