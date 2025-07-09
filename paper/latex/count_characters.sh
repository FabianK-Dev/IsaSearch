words=$(texcount "main.tex")
chars=$(texcount -char "main.tex")

echo "$words"
echo "$chars"

chars=$(echo "$chars" | grep "Letters in text" | awk '{print $NF}')
words=$(echo "$words" | grep "Words in text" | awk '{print $NF}')
total=$((chars + words))

echo "Total: $total"
