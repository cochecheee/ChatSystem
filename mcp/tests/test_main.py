import pytest

@pytest.mark.asyncio
async def test_health_check(client):
    """Kiểm tra endpoint /health xem server và DB đã sẵn sàng chưa"""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": "initialized"}

@pytest.mark.asyncio
async def test_root_endpoint(client):
    """Kiểm tra trang chào mừng của Gateway"""
    response = await client.get("/")
    assert response.status_code == 200
    assert "Welcome to MCP Gateway" in response.json()["message"]