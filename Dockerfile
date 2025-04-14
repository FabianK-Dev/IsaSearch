FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    git \
    curl \
    gzip \
    wget \
    && rm -rf /var/lib/apt/lists/*

RUN wget https://download.oracle.com/graalvm/17/archive/graalvm-jdk-17.0.12_linux-x64_bin.tar.gz \
    && tar -xzf graalvm-jdk-17.0.12_linux-x64_bin.tar.gz -C /opt \
    && rm graalvm-jdk-17.0.12_linux-x64_bin.tar.gz

ENV JAVA_HOME=/opt/graalvm-jdk-17.0.12+8.1
ENV PATH="$JAVA_HOME/bin:$PATH"

RUN echo "deb https://repo.scala-sbt.org/scalasbt/debian all main" | tee /etc/apt/sources.list.d/sbt.list \
    && echo "deb https://repo.scala-sbt.org/scalasbt/debian /" | tee /etc/apt/sources.list.d/sbt_old.list \
    && curl -sL "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x2EE0EA64E40A89B84B2DF73499E82A75642AC823" | tee /etc/apt/trusted.gpg.d/sbt.asc \
    && apt-get update && apt-get install -y sbt \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN git clone https://github.com/Dacit/findfacts.git

WORKDIR /app/findfacts

RUN git clone --depth 1 https://github.com/isabelle-prover/mirror-isabelle.git /app/findfacts/isabelle \
    && isabelle/Admin/init \
    && echo 'ISABELLE_TOOL_JAVA_OPTIONS="-Xms1600m -Xmx2000m"' >> /root/.isabelle/etc/settings \
    && echo 'ML_OPTIONS="--minheap 1800M --maxheap 1800M"' >> /root/.isabelle/etc/settings

ENV PATH="/app/findfacts/isabelle/bin:$PATH"

RUN ./sbt -Dgraal.CompilationFailureAction=Silent -Djdk.util.zip.disableZip64ExtraFieldValidation=true \
    "project importer-isabelle-base" assembly \
    "project search-jedit-base" assembly

#CMD ["./sbt", "-Dgraal.CompilationFailureAction=Silent", "-Djdk.util.zip.disableZip64ExtraFieldValidation=true", "-Dprofiles=memory,loader", "project findfacts", "it:test"]
CMD ["bash"]
