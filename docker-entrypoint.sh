#!/bin/sh
# Create the state directories the image symlinks into. A named volume starts out empty, so without
# this the symlinks under /app dangle - and git refuses to clone into a dangling symlink, which is
# exactly what the first corpus build does with 'afp'.
set -eu

for directory in home .cache artifacts chroma_storages reports afp Isabelle; do
    mkdir -p "/data/$directory"
done

exec "$@"
