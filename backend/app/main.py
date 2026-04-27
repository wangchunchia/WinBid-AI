from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Backend API for WinBid-AI automated bid writing system.",
)

app.include_router(api_router, prefix=settings.api_prefix)

web_dir = Path(__file__).resolve().parent / "web"
assets_dir = web_dir / "assets"
if assets_dir.exists():
    app.mount("/ui/assets", StaticFiles(directory=assets_dir), name="ui-assets")


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": f"{settings.api_prefix}/docs",
    }


@app.get("/ui", include_in_schema=False)
def frontend() -> FileResponse:
    return FileResponse(web_dir / "index.html")
