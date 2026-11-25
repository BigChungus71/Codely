import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.environ['GEMINI_API_KEY'])

try:
    response = genai.embed_content(
        model='models/gemini-embedding-001',
        content=['hello', 'world'],
        task_type='retrieval_document'
    )
    print("KEYS:", response.keys())
    # print small snippet
    if 'embedding' in response:
        print("EMBEDDING SAMPLE:", response['embedding'][0][:2])
        print("LENGTH OF BATCH:", len(response['embedding']))
    else:
        print("NO EMBEDDING KEY. FULL RESP:", response)
except Exception as e:
    import traceback
    with open("error_log.txt", "w") as f:
        f.write("ERROR:\\n" + str(e) + "\\n\\nTRACEBACK:\\n" + traceback.format_exc())
