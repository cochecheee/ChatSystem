import pytest
import asyncio
from httpx import AsyncClient, ASGITransport 
from src.main import app

@pytest.fixture(scope="session")
def event_loop():
    """Tạo vòng lặp sự kiện cho toàn bộ phiên test"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def client():
    """Giả lập một trình duyệt để gọi API FastAPI (REQ-5.1)"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac