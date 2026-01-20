from openai import AsyncOpenAI
from app.core.config import settings
from app.core.exceptions import OpenAIException

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

class OpenAIService:
    async def get_chat_response(self, message: str, model: str) -> str:
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": message}]
            )
            return response.choices[0].message.content
        except Exception as e:
            raise OpenAIException(f"OpenAI API Error: {str(e)}")

openai_service = OpenAIService()
