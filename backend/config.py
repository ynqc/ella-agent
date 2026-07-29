from dataclasses import dataclass
import os
from pathlib import Path


def load_env_file(env_path: Path) -> None:
	if not env_path.exists():
		return

	for raw_line in env_path.read_text(encoding="utf-8").splitlines():
		line = raw_line.strip()
		if not line or line.startswith("#") or "=" not in line:
			continue

		key, value = line.split("=", 1)
		normalized_value = (
			value.strip()
			.replace("\\n", "\n")
			.replace("\\t", "\t")
		)
		os.environ.setdefault(key.strip(), normalized_value)


load_env_file(Path(__file__).with_name(".env"))


@dataclass(frozen=True)
class Settings:
	frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
	ssnc_api_key: str = os.getenv("SSC_CLOUD_API_KEY", "")
	ssnc_case_id: str = os.getenv("SSNC_CASE_ID", "")
	ssnc_base_url: str = os.getenv("SSNC_BASE_URL", "https://api-ai-us.ssnc-corp.cloud/v1")
	ssnc_model: str = os.getenv("SSNC_MODEL", "Qwen/Qwen3-30B-A3B")
	ssnc_temperature: float = float(os.getenv("SSNC_TEMPERATURE", "0"))
	agent_runtime_debug_enabled: bool = os.getenv("AGENT_RUNTIME_DEBUG_ENABLED", "false").lower() in {
		"1",
		"true",
		"yes",
		"on",
	}
	system_prompt: str = os.getenv(
		"ELLA_CHAT_SYSTEM_PROMPT",
		"You are a helpful assistant.",
	)
	database_url: str = os.getenv(
		"DATABASE_URL",
		"postgresql+psycopg://postgres:postgres@localhost:5432/ella_agent",
	)
	memory_ranker_constraint_weight: float = float(os.getenv("MEMORY_RANKER_CONSTRAINT_WEIGHT", "5.0"))
	memory_ranker_preference_weight: float = float(os.getenv("MEMORY_RANKER_PREFERENCE_WEIGHT", "4.0"))
	memory_ranker_profile_weight: float = float(os.getenv("MEMORY_RANKER_PROFILE_WEIGHT", "3.0"))
	memory_ranker_project_weight: float = float(os.getenv("MEMORY_RANKER_PROJECT_WEIGHT", "2.0"))
	memory_ranker_default_weight: float = float(os.getenv("MEMORY_RANKER_DEFAULT_WEIGHT", "1.0"))
	memory_ranker_keyword_hit_weight: float = float(os.getenv("MEMORY_RANKER_KEYWORD_HIT_WEIGHT", "3.0"))
	memory_ranker_content_hit_weight: float = float(os.getenv("MEMORY_RANKER_CONTENT_HIT_WEIGHT", "1.5"))
	memory_ranker_session_bonus: float = float(os.getenv("MEMORY_RANKER_SESSION_BONUS", "1.5"))
	memory_ranker_recent_day_bonus: float = float(os.getenv("MEMORY_RANKER_RECENT_DAY_BONUS", "1.5"))
	memory_ranker_recent_week_bonus: float = float(os.getenv("MEMORY_RANKER_RECENT_WEEK_BONUS", "1.0"))
	memory_ranker_recent_month_bonus: float = float(os.getenv("MEMORY_RANKER_RECENT_MONTH_BONUS", "0.5"))
	memory_context_limit: int = int(os.getenv("MEMORY_CONTEXT_LIMIT", "5"))


settings = Settings()
