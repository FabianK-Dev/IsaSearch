cp .gitignore .dockerignore
echo "" >> .dockerignore
echo "Dockerfile" >> .dockerignore

docker build -t gitlab.lrz.de:5005/kadlez/afp-ai-search .