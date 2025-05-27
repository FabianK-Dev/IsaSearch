cp .gitignore .dockerignore

docker build -t afp-ai-search . \
    && docker run -it afp-ai-search
