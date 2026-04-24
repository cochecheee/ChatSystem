import asyncio
from src.services.llm.client import GeminiClient
from src.services.llm.schemas import AnalysisRequest, AnalysisOutput
from src.services.llm.prompts import SYSTEM_INSTRUCTION, build_prompt

class LLMAnalysisService:
    def __init__(self, client: GeminiClient):
        self.client = client
        # Giới hạn tối đa 3 yêu cầu xử lý cùng lúc
        self._semaphore = asyncio.Semaphore(3)

    async def analyze_vulnerability(self, request: AnalysisRequest) -> AnalysisOutput:
        """Gửi yêu cầu phân tích lỗ hổng sang AI"""
        async with self._semaphore:
            print(f"🧠 AI đang phân tích lỗi: {request.finding_id}...")
            
            # Dựng câu lệnh
            prompt = build_prompt(request)
            
            # Gọi API Gemini
            raw_response_text = await self.client.generate(
                prompt=prompt,
                system_instruction=SYSTEM_INSTRUCTION,
                response_schema=AnalysisOutput
            )
            
            # Trả về kết quả dưới dạng đối tượng Pydantic
            try:
                return AnalysisOutput.model_validate_json(raw_response_text)
            except Exception as e:
                print(f"❌ Lỗi định dạng JSON từ AI: {e}")
                raise e