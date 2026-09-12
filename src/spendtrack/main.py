from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from spendtrack.config import ROOT, load_settings
from spendtrack.routers.api import router as api_router
from spendtrack.routers.frontend import router as frontend_router

cfg = load_settings()

app = FastAPI(title="Spendtrack", version="0.1.0")
app.include_router(frontend_router)
app.include_router(api_router, prefix="/api")

app.mount("/static", StaticFiles(directory=ROOT / "src" / "spendtrack" / "static"), name="static")


def main() -> None:
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=cfg.port)


if __name__ == "__main__":
    main()