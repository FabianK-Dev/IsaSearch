FROM ubuntu:24.04

RUN apt-get update && apt-get install -y \
    wget openjdk-17-jre-headless \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN wget https://www.apache.org/dyn/closer.lua/solr/solr/9.8.1/solr-9.8.1.tgz?action=download -O solr-9.8.1.tgz \
    && tar -xzf solr-9.8.1.tgz \
    && mv solr-9.8.1 /opt/solr \
    && rm solr-9.8.1.tgz

RUN mkdir -p /opt/solr/server/solr/local
ENV SOLR_HOME=/opt/solr
ENV PATH="$SOLR_HOME/bin:$PATH"

# Copy python requirements before copying the rest to allow Docker to cache the layer
COPY requirements.txt /app/

RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Copy assets to the app directory
COPY ./assets /app/assets/

RUN tar -xf assets/artifacts.tar.gz && \
    tar -xf assets/cache.tar.gz && \
    tar -xf assets/chroma_storages.tar.gz && \
    tar -xf assets/find_facts.tar.gz

COPY . /app/

CMD solr start --force -p 8983 -s /opt/solr/server/solr/local && python3 -m benchmark.benchmark