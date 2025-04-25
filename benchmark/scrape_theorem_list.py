from bs4 import BeautifulSoup

import os
import requests
import csv
import json
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

scrape_statistics = {
    "unique_entries": [],
    "unknown_entries": 0,
    "unknwon_entry_urls": []
}

with open(CSV_FILE, mode="w", newline="", encoding="utf-8") as file:
    fieldnames = ['ID', 'Title', 'Theorem', 'Link', 'Entry', 'Title query']
    writer = csv.DictWriter(file, fieldnames=fieldnames)
    writer.writeheader()

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
        
        if "/entries/" in href:
            entry = href.split("/entries/")[1].split(".")[0]
            
            if entry not in scrape_statistics["unique_entries"]:
                scrape_statistics["unique_entries"] = scrape_statistics["unique_entries"] + [entry]
        else:
            entry = "?"
            scrape_statistics["unknown_entries"] += 1

            if href not in scrape_statistics["unknwon_entry_urls"]:
                scrape_statistics["unknwon_entry_urls"] = scrape_statistics["unknwon_entry_urls"] + [href]

        writer.writerow({
            'ID': id_,
            'Title': title,
            'Theorem': inner_text,
            'Link': href,
            'Entry': entry,
            'Title query': title
        })

        print("ID:", id_)
        print("Titel:", title)
        print("Theorem:", inner_text)
        print("Link:", href)
        print("-" * 40)

with open("scrape_statistics.json", "w") as outfile:
    json.dump(scrape_statistics, outfile, indent=4)
