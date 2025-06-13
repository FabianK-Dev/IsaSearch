echo "Python:"
find -name "*.py" -not -path "./.venv/*" -not -path "./afp-*" | xargs wc -l

echo "HTML:"
find -name "*.html" -not -path "./.venv/*" -not -path "./benchmark/*" -not -path "./afp-*" | xargs wc -l

echo "CSV:"
# find -name "*.csv" -not -path "./.venv/*" -not -path "./afp-*" | xargs wc -l
echo "96" # hardcoded because some lines are autowrapped in the CSV files
