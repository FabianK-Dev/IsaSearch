cp .gitignore .dockerignore
echo "" >> .dockerignore
echo "Dockerfile" >> .dockerignore

docker build --build-arg llm_name=microsoft/Phi-3-mini-4k-instruct -t afp-ai-search .