from google import genai
from google.genai import types
from app.config import settings

client = genai.Client(
    api_key=settings.GEMINI_API_KEY,
    http_options={"api_version": "v1"},
)

SYSTEM_PROMPT = """You are a precise document assistant. Answer the user's question using ONLY the context provided below.

Rules:
- If the context does not contain enough information to answer, respond with exactly: "I don't have enough information in the provided documents to answer this question."
- Do not fabricate facts, infer beyond the context, or use external knowledge.
- Be concise and direct.
- Always cite the page number(s) your answer is drawn from, at the end of your response, in the format: [Source: Page X, Page Y]

Context:
{context}
"""


def build_prompt(question: str, chunks: list[dict]) -> str:
    if not chunks:
        return question
    context_parts = []
    for chunk in chunks:
        context_parts.append(f"[Page {chunk['page_number']}]\n{chunk['content']}")
    context = "\n\n---\n\n".join(context_parts)
    return SYSTEM_PROMPT.format(context=context) + f"\n\nQuestion: {question}"


def should_abstain(chunks: list[dict], threshold: float = 0.01) -> bool:
    if not chunks:
        return True
    return chunks[0]["score"] < threshold


def stream_answer(question: str, chunks: list[dict]):
    if should_abstain(chunks):
        yield "I don't have enough information in the provided documents to answer this question."
        return

    prompt = build_prompt(question, chunks)
    for chunk in client.models.generate_content_stream(
        model="gemini-3.6-flash",
        contents=prompt,
    ):
        if chunk.text:
            yield chunk.text
