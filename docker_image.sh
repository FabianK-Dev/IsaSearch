cp .gitignore .dockerignore
echo "" >> .dockerignore
echo "Dockerfile" >> .dockerignore

docker build --build-arg llm_name=microsoft/Phi-3.5-mini-instruct -t afp-ai-search . \
    && docker run --gpus all -it afp-ai-search
