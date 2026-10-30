from fastapi import FastAPI
from app.api.routes import router

app = FastAPI(
    title="Blessing AI Service",
    version="0.1.0",
    description="Independent knowledge and support service for Blessing.",
)
app.include_router(router, prefix="/v1")


@app.get("/")
def root():
    return {
        "service": "blessing-ai-service",
        "status": "starter",
        "docs": "/docs",
        "note": "RAG retrieval and LLM are not configured yet.",
    }
