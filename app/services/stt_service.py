import io
from openai import AsyncOpenAI
from app.core.config import settings
from app.core.exceptions import STTException

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

class STTService:
    async def transcribe_audio(self, audio_data: bytes) -> str:
        try:
            # Create a file-like object from bytes
            audio_file = io.BytesIO(audio_data)
            audio_file.name = "audio.wav" # OpenAI API requires a filename

            transcription = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            )
            return transcription
        except Exception as e:
            raise STTException(f"STT Error: {str(e)}")

stt_service = STTService()
