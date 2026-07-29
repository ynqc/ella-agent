from pydantic import BaseModel, Field


class MeetingWorkflowInput(BaseModel):
	transcript: str = Field(min_length=1, max_length=20000)
	meeting_title: str | None = Field(default=None, max_length=200)
	channel: str = Field(default="engineering", min_length=1, max_length=120)
	send_to_teams: bool = False


class BugWorkflowInput(BaseModel):
	bug_report: str = Field(min_length=1, max_length=20000)
	issue_key: str = Field(min_length=1, max_length=64)
	post_to_jira: bool = False