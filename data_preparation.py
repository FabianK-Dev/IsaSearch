from git import repo

git_url = "https://foss.heptapod.net/isa-afp/afp-devel"
output_folder = "afp-devel-branch-default"

# repo.clone_from(git_url, repo_dir) # TODO

# Use output_folder/thys/ROOTS to get a list of all entries in the AFP
with open(output_folder + "/thys/ROOTS") as file:
    lines = [line.rstrip() for line in file]
    print(lines)
