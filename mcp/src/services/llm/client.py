import os
import asyncio
from google import genai
from google.genai import types

class GeminiClient:
    def __init__(self):
        # Khởi tạo client với API Key từ môi trường
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.client = genai.Client(api_key=self.api_key)
        
        # Cấu hình model và số lần thử lại (Plan 03-01, Task 2)
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.max_retries = int(os.getenv("GEMINI_MAX_RETRIES", "3"))

    async def generate(self, prompt: str, system_instruction: str, response_schema: type) -> str:
        """
        Gửi yêu cầu đến Gemini với cơ chế Retry và Structured Output (Pydantic)
        """
        for attempt in range(self.max_retries):
            try:
                # Gọi API Gemini (sử dụng tính năng Structured Output)
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_schema=response_schema, # Ép AI trả về đúng định dạng class
                    )
                )
                return response.text

            except Exception as e:
                # Xử lý lỗi Rate Limit (429) hoặc Server Overload (503)
                if "429" in str(e) or "503" in str(e):
                    wait_time = 2 ** attempt # Exponential backoff: 1s, 2s, 4s...
                    print(f"⚠️ Gemini API đang bận (Lần thử {attempt + 1}). Thử lại sau {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    # Nếu là lỗi khác thì báo ngay
                    print(f"❌ Lỗi Gemini Client: {e}")
                    raise e
        
        raise RuntimeError(f"Gemini API không phản hồi sau {self.max_retries} lần thử.")