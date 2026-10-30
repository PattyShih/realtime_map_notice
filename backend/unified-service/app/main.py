"""Unified API：將四個微服務掛載為單一 FastAPI 應用的部署設定檔。

用途：Render 免費層的執行個體小時數以「每服務」計，四個服務分開部署
會超出免費額度。此設定檔將四個服務掛載於同一應用（/loc、/event、
/notify、/ai），單一 Starter 執行個體即可運行全部功能，每月 7 美元。

本機的微服務架構（docker-compose）與 Kubernetes 部署不受影響——
這僅是雲端單實例環境的部署設定檔（deployment profile），程式碼為
同一份，四個服務的商業邏輯完全不變。
"""
import asyncio
import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from backend.shared.cors import configure_cors

def _find_base() -> Path:
    # 容器內：/app（main.py 位於 /app/app/）；repo 內：往上级目錄搜尋
    # 含 backend/location-service 的目錄，兩種環境皆可用
    current = Path(__file__).resolve().parent
    for candidate in [current.parent, *current.parent.parents]:
        if (candidate / "backend/location-service/app/main.py").exists():
            return candidate
    return current.parent.parent


BASE = _find_base()  # 容器內為 /app


def _load(rel: str, name: str):
    """以 importlib 載入服務模組（服務目錄名含連字號，無法直接 import）。"""
    spec = importlib.util.spec_from_file_location(name, BASE / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# 單實例內部呼叫走 localhost（不出容器、不受對外網址異動影響）；
# 若環境已明確設定（如分離部署），則尊重既有值
import os

os.environ.setdefault("AI_SERVICE_URL", "http://localhost:8000/ai")
os.environ.setdefault("NOTIFICATION_SERVICE_URL", "http://localhost:8000/notify")

location = _load("backend/location-service/app/main.py", "unified_location")
event = _load("backend/event-service/app/main.py", "unified_event")
notification = _load("backend/notification-service/app/main.py", "unified_notification")
ai = _load("backend/ai-service/app/main.py", "unified_ai")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 掛載的子應用之 lifespan 不會被 Starlette 執行，
    # 因此在此手動啟動 location 服務的幽靈使用者清掃任務
    task = asyncio.create_task(location.cleanup_stale_locations())
    yield
    task.cancel()


app = FastAPI(
    title="realtime_map_notice Unified API",
    version="1.0.0",
    lifespan=lifespan,
)
configure_cors(app)


@app.get("/healthz")
async def healthz() -> dict[str, object]:
    return {
        "status": "ok",
        "mode": "unified",
        "services": ["location", "event", "notification", "ai"],
    }


app.mount("/loc", location.app)
app.mount("/event", event.app)
app.mount("/notify", notification.app)
app.mount("/ai", ai.app)
