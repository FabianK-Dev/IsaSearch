texcount -char "main.tex"

chars=$(texcount -char "main.tex" | grep "Letters in text" | awk '{print $NF}')
words=$(texcount "main.tex" | grep "Words in text" | awk '{print $NF}')
total=$((chars + words))

echo "Total: $total"
