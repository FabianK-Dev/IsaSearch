import glob

def load_prompts(config):
    prompts_folder = config["prompts_folder"]

    for file in glob.glob(prompts_folder + "/*.txt"):
        print(file)
