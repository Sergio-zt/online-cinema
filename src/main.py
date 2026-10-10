from fastapi import FastAPI

app = FastAPI(
    title="Online Cinema API",
    version="0.1.0",
    description="Backend API for online cinema platform",
)


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Check the health status of the application."""
    return {"status": "ok"}