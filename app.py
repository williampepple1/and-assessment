import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from meridian_chatbot.api import router as api_router
from meridian_chatbot.config import get_settings
from meridian_chatbot.logging_config import configure_logging


settings = get_settings()
configure_logging(settings)

app = FastAPI(
    title="Meridian Electronics Support Chatbot",
    description="Tool-grounded customer support chatbot using an MCP server.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")

static_dir = Path(__file__).parent / "frontend" / "dist"
if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/{path:path}", response_model=None)
async def serve_react_app(path: str) -> FileResponse | dict[str, str]:
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Frontend build not found. Run npm run build in frontend/."}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
