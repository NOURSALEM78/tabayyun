"""Expose the Tabayyun FastAPI application and health endpoints."""

from fastapi import FastAPI

from backend.api.routes import router

app = FastAPI(title="Tabayyun API")
app.include_router(router)


@app.get("/")
def home() -> dict[str, str]:
    """Return the API welcome message."""
    return {"message": "مرحبا، هذا نظام تبيّن"}


@app.get("/api/health")
def health() -> dict[str, str]:
    """Return the API health status."""
    return {"status": "ok"}
