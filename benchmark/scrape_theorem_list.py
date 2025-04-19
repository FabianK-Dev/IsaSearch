from bs4 import BeautifulSoup

import os
import requests
import csv
import re

URL = "https://cgi.cse.unsw.edu.au/~kleing/top100/"
CACHE_FILE = "top100.html"
CSV_FILE = "top100_data.csv"

if not os.path.exists(CACHE_FILE):
    response = requests.get(URL)
    with open(CACHE_FILE, "w") as file:
        file.write(response.text)

with open(CACHE_FILE, "r") as file:
    soup = BeautifulSoup(file, "html.parser")

with open(CSV_FILE, mode="w", newline="", encoding="utf-8") as file:
    fieldnames = ['ID', 'Title', 'Theorem', 'Link', 'Title query']
    writer = csv.DictWriter(file, fieldnames=fieldnames)
    writer.writeheader()

    i = 0
    for h2 in soup.find_all("h2"):
        id_ = h2.get("id", "")
        title = h2.get_text(strip=True)
        title = re.compile(r"^\d+\.\s*").sub("", title)
        title = re.compile(r"\n+").sub(" ", title)

        code_div = h2.find_next("div", class_="highlight")
        inner_text = code_div.get_text(strip=False) if code_div else "?"
        #inner_text = inner_text.split("\n")[0]

        prev_a = h2.find_next("a", class_="uri")
        href = prev_a.get("href", "") if prev_a else "?"

        if "isa-afp.org" not in href:
            continue

        i += 1
        if i > 10:
            break

        writer.writerow({
            'ID': id_,
            'Title': title,
            'Theorem': inner_text,
            'Link': href,
            'Title query': title
        })

        print("ID:", id_)
        print("Titel:", title)
        print("Theorem:", inner_text)
        print("Link:", href)
        print("-" * 40)
