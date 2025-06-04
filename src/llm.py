from pathlib import Path
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
import glob
import json

def load_prompts(config):
    prompts_folder = config["prompts_folder"]
    prompts = {}

    for file in glob.glob(prompts_folder + "/*.txt"):
        prompt_name = Path(file).stem

        with open(file, "r") as file:
            data = file.read()
            prompts[prompt_name] = data

    return prompts

def save_llm_output_cache(llm_output_cache, config):
    print("Saving LLM output cache...")

    CACHE_FOLDER = config["cache_folder"]
    LLM_OUTPUT_CACHE = f"{CACHE_FOLDER}/llm_output_cache.json"

    with open(LLM_OUTPUT_CACHE, "w") as file:
        json.dump(llm_output_cache, file, indent=4)

def get_llm(config):
    model = AutoModelForCausalLM.from_pretrained(
        config["llm_name"],
        device_map="auto",
        torch_dtype="auto")

    tokenizer = AutoTokenizer.from_pretrained(config["llm_name"])

    pipe = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer)

    generation_args = {
        "max_new_tokens": config["sampling_parameters"]["max_tokens"],
        "return_full_text": False,
        "do_sample": False
    }

    return pipe, generation_args