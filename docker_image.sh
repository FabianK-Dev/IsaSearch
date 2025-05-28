cp .gitignore .dockerignore
echo "" >> .dockerignore
echo "Dockerfile" >> .dockerignore

docker build -t afp-ai-search . \
    && docker run -it afp-ai-search
