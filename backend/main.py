"""Expose the Tabayyun FastAPI application and, once built, the web interface.

After ``npm run build`` in frontend/, the interface in frontend/dist is served at "/",
so the whole system runs from one address. Without a build, "/" returns a short
message and the interface runs separately with ``npm run dev`` (port 5173).
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.api.routes import router

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

app = FastAPI(title="Tabayyun API")
app.include_router(router)


@app.get("/api/health")
def health() -> dict[str, str]:
    """Return the API health status."""
    return {"status": "ok"}


if (FRONTEND_DIST / "index.html").exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="interface")
else:

    @app.get("/")
    def home() -> dict[str, str]:
        """Return the API welcome message (the interface has not been built)."""
        return {"message": "مرحبا، هذا نظام تبيّن"}
