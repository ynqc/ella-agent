import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.workflows import router as workflow_router
from app.memory.database import init_db
from config import settings


def configure_application_logging() -> None:
	logging.getLogger("app.llm.client").setLevel(logging.INFO)
	logging.getLogger("llm.client").setLevel(logging.INFO)


configure_application_logging()
init_db()

app = FastAPI(title="Ella Agent API")

app.add_middleware(
	CORSMiddleware,
	allow_origins=[settings.frontend_origin],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(workflow_router)


@app.get("/health")
async def healthcheck() -> dict[str, str]:
	return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")