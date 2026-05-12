import json
from tqdm import tqdm
from openai import OpenAI
from text2music.inference.prompt import get_llm_prompt
import argparse

if __name__ == "__main__":

    # Define args
    parser = argparse.ArgumentParser()
    parser.add_argument('--api_key', type=str, required=False, help='OpenAI API key for verifying the header')
    parser.add_argument('--input_json', type=str, default="/data/home/acw769/text2score/text2music/artifacts/prompts/prompts_with_ids.json", help='Path to the json file containing the prompt information')
    parser.add_argument('--output_json', type=str, default="/data/home/acw769/text2score/text2music/artifacts/prompts/prompts_with_plan.json", help='Path to the json file to save the prompt information with plans')
    args = parser.parse_args()

    client = OpenAI(api_key=args.api_key)

    # 1. Read the JSON file
    with open(args.input_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    for item in tqdm(data):

        if "openai_plan" not in item.keys():
        
            prompt = get_llm_prompt(item['prompt'])
        
            plan = client.responses.create(
                # model="gpt-5.4-mini",
                model="gpt-5.1",
                input=prompt
            )
            item["openai_plan"] = plan.output_text

    # 3. Write it back to a file
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)