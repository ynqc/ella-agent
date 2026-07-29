import json
from dataclasses import dataclass
from typing import Any

from app.memory.database import SessionLocal
from app.workflows.base import WorkflowRunResult
from app.workflows.cache_repository import WorkflowArtifactCacheRepository
from app.workflows.utils import normalize_multiline_text, optional_text, sha256_hexdigest


@dataclass(frozen=True)
class WorkflowCacheHit:
	input_hash: str
	normalized_input: str
	result: WorkflowRunResult


class WorkflowArtifactCacheService:
	def _cache_metadata(self, *, workflow_type: str, normalized_input: str, cache_scope: str) -> dict[str, str]:
		return {
			"workflow_type": workflow_type,
			"input_hash": sha256_hexdigest(normalized_input),
			"normalized_input": normalized_input,
			"cache_scope": cache_scope,
		}

	def build_meeting_cache_metadata(
		self,
		*,
		meeting_title: str | None,
		transcript: str,
		channel: str,
		send_to_teams: bool,
	) -> dict[str, str | bool]:
		_ = channel
		_ = send_to_teams
		return self._cache_metadata(
			workflow_type="meeting",
			normalized_input=self.normalize_transcript(transcript),
			cache_scope=self.build_meeting_cache_scope(
				meeting_title=meeting_title,
				channel=channel,
				send_to_teams=send_to_teams,
			),
		)

	def build_bug_cache_metadata(
		self,
		*,
		bug_report: str,
		issue_key: str,
		post_to_jira: bool,
	) -> dict[str, str]:
		_ = post_to_jira
		return self._cache_metadata(
			workflow_type="bug",
			normalized_input=self.normalize_bug_report(bug_report),
			cache_scope=self.build_bug_cache_scope(issue_key=issue_key, post_to_jira=post_to_jira),
		)

	def normalize_transcript(self, transcript: str) -> str:
		return normalize_multiline_text(transcript)

	def normalize_bug_report(self, bug_report: str) -> str:
		return normalize_multiline_text(bug_report)

	def build_meeting_cache_scope(
		self,
		*,
		meeting_title: str | None,
		channel: str,
		send_to_teams: bool,
	) -> str:
		_ = channel
		_ = send_to_teams
		scope_payload = {
			"meeting_title": optional_text(meeting_title),
		}
		return json.dumps(scope_payload, ensure_ascii=False, sort_keys=True)

	def build_bug_cache_scope(self, *, issue_key: str, post_to_jira: bool) -> str:
		_ = post_to_jira
		scope_payload = {
			"issue_key": optional_text(issue_key),
		}
		return json.dumps(scope_payload, ensure_ascii=False, sort_keys=True)

	def _content_only_result(self, result: WorkflowRunResult, *, content_step_names: set[str], content_artifact_keys: set[str]) -> WorkflowRunResult:
		filtered_steps = [step for step in result.steps if step.step_name in content_step_names]
		filtered_artifacts = {
			key: value
			for key, value in result.artifacts.items()
			if key in content_artifact_keys
		}
		return result.with_steps(filtered_steps).with_artifacts(filtered_artifacts).with_cache(None)

	def _meeting_content_only_result(self, result: WorkflowRunResult) -> WorkflowRunResult:
		return self._content_only_result(
			result,
			content_step_names={"summary", "action_items", "memo"},
			content_artifact_keys={"transcript", "summary", "action_items", "memo"},
		)

	def _bug_content_only_result(self, result: WorkflowRunResult) -> WorkflowRunResult:
		return self._content_only_result(
			result,
			content_step_names={"analysis", "root_cause", "jira_comment"},
			content_artifact_keys={"bug_report", "analysis", "root_cause", "jira_comment"},
		)

	def _lookup_result(self, *, workflow_type: str, input_hash: str, cache_scope: str) -> WorkflowRunResult | None:
		session = SessionLocal()
		try:
			record = WorkflowArtifactCacheRepository(session).get_by_scope(workflow_type, input_hash, cache_scope)
		finally:
			session.close()

		if record is None:
			return None

		return WorkflowRunResult.from_dict(json.loads(record.result_json))

	def _store_result(
		self,
		*,
		workflow_type: str,
		session_id: str,
		input_hash: str,
		normalized_input: str,
		cache_scope: str,
		result: WorkflowRunResult,
	) -> None:
		session = SessionLocal()
		try:
			WorkflowArtifactCacheRepository(session).save_or_update(
				workflow_type=workflow_type,
				session_id=session_id,
				input_hash=input_hash,
				normalized_input=normalized_input,
				cache_scope=cache_scope,
				result_json=json.dumps(result.to_dict(), ensure_ascii=False),
			)
		finally:
			session.close()

	def lookup_meeting_result(
		self,
		*,
		meeting_title: str | None,
		transcript: str,
		channel: str,
		send_to_teams: bool,
	) -> WorkflowCacheHit | None:
		cache_metadata = self.build_meeting_cache_metadata(
			meeting_title=meeting_title,
			transcript=transcript,
			channel=channel,
			send_to_teams=send_to_teams,
		)

		cached_result = self._lookup_result(
			workflow_type="meeting",
			input_hash=str(cache_metadata["input_hash"]),
			cache_scope=str(cache_metadata["cache_scope"]),
		)
		if cached_result is None:
			return None
		return WorkflowCacheHit(
			input_hash=str(cache_metadata["input_hash"]),
			normalized_input=str(cache_metadata["normalized_input"]),
			result=cached_result,
		)

	def store_meeting_result(
		self,
		*,
		session_id: str,
		meeting_title: str | None,
		transcript: str,
		channel: str,
		send_to_teams: bool,
		result: WorkflowRunResult,
	) -> None:
		cache_metadata = self.build_meeting_cache_metadata(
			meeting_title=meeting_title,
			transcript=transcript,
			channel=channel,
			send_to_teams=send_to_teams,
		)
		self._store_result(
			workflow_type="meeting",
			session_id=session_id,
			input_hash=str(cache_metadata["input_hash"]),
			normalized_input=str(cache_metadata["normalized_input"]),
			cache_scope=str(cache_metadata["cache_scope"]),
			result=self._meeting_content_only_result(result),
		)

	def lookup_bug_result(
		self,
		*,
		bug_report: str,
		issue_key: str,
		post_to_jira: bool,
	) -> WorkflowCacheHit | None:
		cache_metadata = self.build_bug_cache_metadata(
			bug_report=bug_report,
			issue_key=issue_key,
			post_to_jira=post_to_jira,
		)
		cached_result = self._lookup_result(
			workflow_type="bug",
			input_hash=str(cache_metadata["input_hash"]),
			cache_scope=str(cache_metadata["cache_scope"]),
		)
		if cached_result is None:
			return None
		return WorkflowCacheHit(
			input_hash=str(cache_metadata["input_hash"]),
			normalized_input=str(cache_metadata["normalized_input"]),
			result=cached_result,
		)

	def store_bug_result(
		self,
		*,
		session_id: str,
		bug_report: str,
		issue_key: str,
		post_to_jira: bool,
		result: WorkflowRunResult,
	) -> None:
		cache_metadata = self.build_bug_cache_metadata(
			bug_report=bug_report,
			issue_key=issue_key,
			post_to_jira=post_to_jira,
		)
		self._store_result(
			workflow_type="bug",
			session_id=session_id,
			input_hash=str(cache_metadata["input_hash"]),
			normalized_input=str(cache_metadata["normalized_input"]),
			cache_scope=str(cache_metadata["cache_scope"]),
			result=self._bug_content_only_result(result),
		)