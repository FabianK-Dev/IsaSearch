from bs4 import BeautifulSoup

import os
import requests
import csv

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
    fieldnames = ['ID', 'Title', 'Theorem', 'Link']
    writer = csv.DictWriter(file, fieldnames=fieldnames)
    writer.writeheader()

    for h2 in soup.find_all("h2"):
        print(h2)
