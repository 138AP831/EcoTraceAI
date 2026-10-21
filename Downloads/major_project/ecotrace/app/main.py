"""FastAPI application factory for EcoTrace AI."""
from fastapi import FastAPI

from app.routers import badges, collections, facilities, marketplace, producers

app = FastAPI(title="EcoTrace AI", version="0.1.0")

app.include_router(facilities.router)
app.include_router(producers.router)
app.include_router(collections.router)
app.include_router(badges.router)
app.include_router(marketplace.router)


@app.get("/health")
def health():
    return {"status": "ok"}
