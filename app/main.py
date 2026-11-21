from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.services.retrieval import get_retrieval_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_retrieval_store()
    yield


app = FastAPI(
    title="Blessing AI Service",
    version="0.1.0",
    description="Independent knowledge and support service for Blessing.",
    lifespan=lifespan,
)

app.include_router(router, prefix="/v1")


@app.get("/")
def root():
    return {
        "service": "blessing-ai-service",
        "status": "running",
        "docs": "/docs",
    }
