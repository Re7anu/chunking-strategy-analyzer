from google import genai
from google.genai import types

from src.config.settings import GEMINI_API_KEY, CHAT_MODEL_NAME, CHAT_TEMPERATURE
from src.clients.prompts import RAG_SYSTEM_INSTRUCTION_TEMPLATE, CONVERSATION_TITLE_PROMPT_TEMPLATE

if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY environment variable is not set!")

# Initialize Google GenAI client using the key loaded in settings.py
client = genai.Client(api_key=GEMINI_API_KEY)


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

def generate_conversation_title(question: str) -> str:
    """
    Generates a concise 3-5 word conversation title from the first question.
    """
    try:
        prompt = CONVERSATION_TITLE_PROMPT_TEMPLATE.format(question=question)
        response = client.models.generate_content(
            model=CHAT_MODEL_NAME,
            contents=prompt
        )
        title = response.text.strip().replace('"', '').replace("'", "")
        # Truncate if model hallucinates a long paragraph
        if len(title) > 40:
            title = title[:37] + "..."
        return title if title else "New Chat"
    except Exception as e:
        print(f"Error auto-generating conversation title: {e}")
        # Fallback to simple truncation
        return question[:25] + "..." if len(question) > 25 else question
