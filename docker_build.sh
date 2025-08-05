cp .gitignore .dockerignore
echo "" >> .dockerignore
echo "Dockerfile" >> .dockerignore

# Remove the line assets_extracted/* from .dockerignore
sed -i '/assets_extracted/d' .dockerignore

echo "Extracting assets to assets_extracted/"
mkdir -p assets_extracted

# --keep-newer-files makes sure tar.gz files are only extracted if they are newer then folders in assets_extracted/
tar --keep-newer-files -xf ./assets/afp-2025-branch-default.tar.gz -C assets_extracted/
tar --keep-newer-files -xf ./assets/chroma_storages.tar.gz -C assets_extracted/
tar --keep-newer-files -xf ./assets/find_facts.tar.gz -C assets_extracted/

docker build -t gitlab.lrz.de:5005/kadlez/afp-ai-search .
docker images gitlab.lrz.de:5005/kadlez/afp-ai-search
docker history gitlab.lrz.de:5005/kadlez/afp-ai-search
