import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.workflows import router as workflow_router
from app.api.dependencies import init_services
from app.mcp.manager import MCPManager
from app.memory.database import init_db
from config import settings

logger = logging.getLogger(__name__)


def configure_application_logging() -> None:
	logging.getLogger("app.llm.client").setLevel(logging.INFO)
	logging.getLogger("llm.client").setLevel(logging.INFO)


configure_application_logging()
init_db()

mcp_manager: MCPManager | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
	global mcp_manager
	mcp_manager = MCPManager()
	try:
		await mcp_manager.connect()
		logger.info("MCP manager started: %d tools available", len(mcp_manager.list_tools()))
	except Exception as exc:
		logger.error("MCP manager failed to start: %s", exc)
		mcp_manager = None

	init_services(mcp_manager=mcp_manager)

	yield

	if mcp_manager:
		await mcp_manager.shutdown()
		logger.info("MCP manager shut down")


app = FastAPI(title="Ella Agent API", lifespan=lifespan)

app.add_middleware(
	CORSMiddleware,
	allow_origins=[settings.frontend_origin],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(workflow_router)


def get_mcp_manager() -> MCPManager | None:
	return mcp_manager


@app.get("/health")
async def healthcheck() -> dict[str, str]:
	return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")