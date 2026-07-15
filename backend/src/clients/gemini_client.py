import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

from src.config.settings import CHAT_MODEL_NAME, CHAT_TEMPERATURE
from src.prompts import RAG_SYSTEM_INSTRUCTION_TEMPLATE

load_dotenv()

# Initialize Google GenAI client
# It automatically reads GEMINI_API_KEY from environment variables
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("WARNING: GEMINI_API_KEY environment variable is not set!")
client = genai.Client(api_key=api_key)

def get_chat_stream(question: str, context: str, history: list = None):
    """
    Generates a streaming response for the customer support chat using Gemini models.
    """
    if history is None:
        history = []

    contents = []
    
    # Port history objects into GenAI Content types
    # Expected history item: {"role": "user" | "model", "content": "text"}
    for msg in history:
        role = "user" if msg.get("role") == "user" else "model"
        contents.append(
            types.Content(
                role=role,
                parts=[types.Part.from_text(text=msg.get("content", ""))]
            )
        )

    # Context-enhanced system instruction
    system_instruction = RAG_SYSTEM_INSTRUCTION_TEMPLATE.format(context=context)

    # Append current question
    contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=question)]
        )
    )

    # Stream generation
    return client.models.generate_content_stream(
        model=CHAT_MODEL_NAME,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=CHAT_TEMPERATURE
        )
    )
