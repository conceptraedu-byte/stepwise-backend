import json
import re


def safe_json_extract(text, expect="object"):
    try:
        if expect == "object":
            start = text.find("{")
            end = text.rfind("}")
        else:
            start = text.find("[")
            end = text.rfind("]")

        if start == -1 or end == -1:
            return {} if expect == "object" else []

        json_str = text[start:end + 1]

        # try direct
        try:
            return json.loads(json_str)
        except:
            pass

        # 🔧 fix common issues
        json_str = json_str.replace("\n", " ")

        # remove trailing broken strings
        json_str = re.sub(r'"[^"]*$', '"', json_str)

        # remove trailing broken objects
        json_str = re.sub(r',\s*{[^}]*$', '', json_str)

        return json.loads(json_str)

    except Exception as e:
        print("SAFE JSON FAILED:", e)
        return {} if expect == "object" else []