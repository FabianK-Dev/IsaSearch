# The image holds the code and its Python dependencies and nothing else. Everything that is written
# at run time - the Isabelle and AFP checkouts, ~/.isabelle with its contrib and the FindFacts Solr
# core, the caches, the artifacts and the ChromaDB storages - lives on the /data volume. The same
# image serves all three roles (corpus build, web application, duplicate detection); they differ
# only in the command they are started with.
FROM python:3.11-slim

# git clones and updates the AFP (src/installation.py). Isabelle is installed from its release
# archive, which bundles both contrib and a JDK, so no wget and no JRE are needed here.
#
# fontconfig and a font family are needed even though nothing here draws anything: Isabelle's JVM
# initializes AWT during 'isabelle find_facts_index' and aborts with "Fontconfig head is null" on a
# system that has no fonts at all, which a slim base image does not.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates fontconfig fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy python requirements before copying the rest to allow Docker to cache the layer
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Every path in config.json is relative and resolved against the working directory, so the state
# directories are symlinked out of /app instead of the config being rewritten for the container.
# ~/.isabelle follows via HOME. The entrypoint creates the targets before the command runs.
ENV HOME=/data/home
RUN set -eu; \
    for directory in .cache artifacts chroma_storages reports afp Isabelle; do \
        ln -s "/data/$directory" "/app/$directory"; \
    done

COPY benchmark /app/benchmark
COPY prompts /app/prompts
COPY src /app/src
COPY tests /app/tests
COPY config.json /app/config.json
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 5001

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "-m", "src.app"]
