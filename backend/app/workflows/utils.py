import json
import hashlib
import re
from typing import Any


def strip_code_fence(text: str) -> str:
	stripped = text.strip()
	if not stripped.startswith("```"):
		return stripped

	lines = stripped.splitlines()
	if len(lines) >= 2 and lines[-1].strip() == "```":
		return "\n".join(lines[1:-1]).strip()
	return stripped


def load_json_object(text: str, label: str) -> dict[str, Any]:
	payload = strip_code_fence(text)
	parsed = json.loads(payload)
	if not isinstance(parsed, dict):
		raise ValueError(f"{label} output must be a JSON object.")
	return parsed


def string_list(value: object) -> list[str]:
	if not isinstance(value, list):
		return []

	items: list[str] = []
	for item in value:
		if not isinstance(item, str):
			continue
		normalized = item.strip()
		if normalized:
			items.append(normalized)
	return items


def optional_text(value: object) -> str:
	if not isinstance(value, str):
		return ""
	return value.strip()


def normalize_multiline_text(text: str) -> str:
	normalized_newlines = text.replace("\r\n", "\n").replace("\r", "\n")
	lines = normalized_newlines.split("\n")
	normalized_lines: list[str] = []
	previous_blank = False

	for line in lines:
		normalized_line = re.sub(r"\s+", " ", line.strip())
		if not normalized_line:
			if previous_blank:
				continue
			previous_blank = True
			normalized_lines.append("")
			continue

		previous_blank = False
		normalized_lines.append(normalized_line)

	return "\n".join(normalized_lines).strip()


def sha256_hexdigest(text: str) -> str:
	return hashlib.sha256(text.encode("utf-8")).hexdigest()