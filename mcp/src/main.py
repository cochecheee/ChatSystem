from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv

# --- [THÊM MỚI - PLAN 01] ---
from contextlib import asynccontextmanager
from src.core.db import init_db 
# ---------------------------

# --- [THÊM MỚI - PLAN 04] ---
from src.api.artifacts import router as artifact_router
# ---------------------------

# --- [THÊM MỚI - PLAN 04 - TASK 3] Import thư viện cho Poller ---
import asyncio
from src.services.poller import GitHubPoller
from src.core.db import AsyncSessionLocal # Factory để tạo kết nối DB cho Poller
# ---------------------------------------------------------------

load_dotenv()

# --- [CHỈNH SỬA - PLAN 01 & 04] Tích hợp Lifespan để quản lý DB & Poller ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Khởi tạo các bảng Database khi server bắt đầu chạy (Plan 01)
    print("🚀 [PHASE 2] Initializing Database tables...")
    await init_db()
    
    # 2. Khởi chạy Poller quét GitHub tự động mỗi 5 phút (Plan 04 - Task 3)
    # Chúng ta dùng asyncio.create_task để nó chạy ngầm mà không làm treo API
    print("🕵️ [PLAN 04] Starting GitHub Poller background task...")
    poller = GitHubPoller(db_session_factory=AsyncSessionLocal)
    asyncio.create_task(poller.start()) 
    
    yield
    print("🛑 [PHASE 2] Shutting down server...")

# Khởi tạo ứng dụng FastAPI với lifespan
app = FastAPI(
    title="MCP Gateway", 
    description="Security-Integrated CI/CD Middleware",
    lifespan=lifespan
)
# -----------------------------------------------------------------

# Configure CORS for Dashboard (Giữ nguyên gốc)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- [THÊM MỚI - PLAN 04] Tích hợp các API xử lý bảo mật ---
app.include_router(artifact_router)
# ---------------------------------------------------------

@app.get("/")
async def root():
    # Cập nhật thông tin trả về để phản ánh hệ thống đã hoàn thiện Phase 2
    return {
        "message": "Welcome to MCP Gateway", 
        "status": "running",
        "current_phase": "02-mcp-gateway",
        "status_detail": "Phase 2 Core completed (DB, GitHub Sync, Guardrails, Normalizers, Poller)"
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "database": "initialized"}

if __name__ == "__main__":
    import uvicorn
    # Giữ nguyên cấu trúc chạy server
    uvicorn.run(app, host="0.0.0.0", port=8000)