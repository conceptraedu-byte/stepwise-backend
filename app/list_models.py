import os
from dotenv import load_dotenv
import google.generativeai as genai

# ✅ LOAD .env explicitly
load_dotenv()

# ✅ NOW this will work
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

models = genai.list_models()

print("\nAVAILABLE MODELS:\n")
for m in models:
    print(m.name, "->", m.supported_generation_methods)
