import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.environ['GEMINI_API_KEY'])

try:
    response = genai.GenerativeModel('gemini-3-flash-preview').generate_content('hello')
    print("SUCCESS:", response.text)
except Exception as e:
    print("ERROR:", e)
