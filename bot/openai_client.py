from openai import OpenAI
from bot.config import load_config

config = load_config()
openai_client = OpenAI(api_key=config["OPENAI_API_KEY"])
