AFP_FOLDER = "afp-2025-04-13"

entries = []

with open(AFP_FOLDER + "/thys/ROOTS") as entries_file:
    for line in entries_file:
        entries.append(line.rstrip())

print("Entries:")
print(entries)
