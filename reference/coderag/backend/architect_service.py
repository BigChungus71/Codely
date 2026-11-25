import os
import google.generativeai as genai

# Setup Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

class ArchitectService:
    def __init__(self):
        self.model = genai.GenerativeModel(MODEL_NAME)

    def generate_report(self, input_text: str, action: str, context_chunks: list[str]) -> str:
        """Central router for the 3 Architect features."""
        
        context_str = "\n".join([f"--- Chunk ---\n{c}" for c in context_chunks])

        if action == "blast_radius":
            prompt = f"""You are a Principal Software Architect.
Perform a Semantic Blast Radius Analysis on the following selected code.
Determine what other files, components, or services will be impacted if this code is modified or deleted. Base your answer EXCLUSIVELY on the retrieved codebase context provided below.

### SELECTED CODE ###
{input_text}

### RETRIEVED REPOSITORY CONTEXT ###
{context_str}

Format your output in clean, professional Markdown. Group impacts by severity (High, Medium, Low).
"""
        elif action == "debug":
            prompt = f"""You are a Principal Debugging Engineer.
A developer encountered the following error log/stack trace. Pinpoint the root cause using the provided repository context.
Explain EXACTLY which file caused this and provide the exact code modification required to fix it.

### ERROR LOG/TRACE ###
{input_text}

### RETRIEVED REPOSITORY CONTEXT ###
{context_str}

Format your output in clean Markdown. Include a section for "Root Cause" and "Suggested Fix (Diff)".
"""
        elif action == "review":
            prompt = f"""You are a strict, Principal Code Reviewer.
Review the following active file. Your job is to enforce internal repository conventions, abstract patterns, and wrappers. 
Look at the retrieved repository context to understand how the rest of the codebase handles similar logic. Point out any deviations where this specific file ignores established abstractions.

### ACTIVE FILE CONTENT ###
{input_text}

### REPOSITORY DESIGN PATTERNS (RETRIEVED CONTEXT) ###
{context_str}

Format your output in clean Markdown. Point out violations and suggest the refactored code that conforms to repository standards.
"""
        else:
            return "Invalid action selected."

        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"**Architect Error:** {str(e)}"
