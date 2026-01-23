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
        
     # 🔥 RP / QA용 (messages 리스트 지원)
    async def rpchat(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int = 120,
        temperature: float = 0.4,
        top_p: float = 0.9,
        frequency_penalty: float = 0.3,
    ) -> str:
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                frequency_penalty=frequency_penalty,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            raise OpenAIException(f"OpenAI API Error: {str(e)}")

openai_service = OpenAIService()
