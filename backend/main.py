from fastapi import FastAPI

app = FastAPI(title="Tabayyun API")


@app.get("/")
def home():
    return {"message": "مرحبا، هذا نظام تبيّن"}


@app.get("/api/health")
def health():
    return {"status": "ok"}