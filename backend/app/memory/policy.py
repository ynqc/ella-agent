from dataclasses import dataclass

from config import settings


@dataclass(frozen=True)
class MemoryPolicy:
    context_memory_limit: int = 5

    def type_weight(self, memory_type: str) -> float:
        if memory_type == "constraint":
            return settings.memory_ranker_constraint_weight
        if memory_type == "preference":
            return settings.memory_ranker_preference_weight
        if memory_type == "profile":
            return settings.memory_ranker_profile_weight
        if memory_type == "project":
            return settings.memory_ranker_project_weight
        return settings.memory_ranker_default_weight

    def conflict_key(self, memory_type: str, content: str) -> str:
        normalized_content = content.lower().strip()

        if memory_type == "preference":
            if "中文" in normalized_content or "english" in normalized_content or "英文" in normalized_content:
                return "language-preference"
            if "简洁" in normalized_content or "详细" in normalized_content:
                return "response-style"

        if memory_type == "profile":
            if "姓名" in normalized_content or "名字" in normalized_content or normalized_content.startswith("用户叫"):
                return "profile-name"
            if "职业" in normalized_content or "岗位" in normalized_content:
                return "profile-role"
            if "团队" in normalized_content or "组别" in normalized_content:
                return "profile-team"

        if memory_type == "constraint":
            if "chatgpt" in normalized_content or "自称" in normalized_content or "身份" in normalized_content:
                return "identity-constraint"
            if "不要提及" in normalized_content or "不要透露" in normalized_content:
                return "disclosure-constraint"

        return normalized_content