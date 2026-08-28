import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

type ArtifactEvent = {
  type: 'artifact'
  artifact_key: string
  artifact: unknown
  step_name: string
  step_status: string
  workflow_type: string
  duration_ms: number
}

type ArtifactCardProps = {
  artifact: ArtifactEvent
}

const ARTIFACT_TITLES: Record<string, string> = {
  analysis: 'Bug Analysis',
  root_cause: 'Root Cause',
  jira_comment: 'Jira Comment',
  jira_delivery: 'Jira Delivery',
  summary: 'Meeting Summary',
  action_items: 'Action Items',
  memo: 'Meeting Memo',
  memory_record: 'Memory Saved',
  teams_delivery: 'Teams Delivery',
}

const ARTIFACT_ICONS: Record<string, string> = {
  analysis: '\u{1F50D}',
  root_cause: '\u{1F3AF}',
  jira_comment: '\u{1F4DD}',
  jira_delivery: '\u{2705}',
  summary: '\u{1F4CB}',
  action_items: '\u{2611}️',
  memo: '\u{1F4C4}',
  memory_record: '\u{1F4BE}',
  teams_delivery: '\u{1F4E8}',
}

function getBadgeClass(status: string): string {
  switch (status) {
    case 'success':
      return 'artifact-badge artifact-badge-success'
    case 'skipped':
      return 'artifact-badge artifact-badge-skipped'
    case 'failed':
      return 'artifact-badge artifact-badge-failed'
    default:
      return 'artifact-badge'
  }
}

function StringList({ label, items }: { label: string; items: string[] }) {
  if (!items || items.length === 0) return null
  return (
    <div>
      <p className="artifact-kv-label">{label}</p>
      <ul>
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  )
}

function AnalysisRenderer({ data }: { data: Record<string, unknown> }) {
  return (
    <div>
      {data.summary && <p>{String(data.summary)}</p>}
      <StringList label="Symptoms" items={data.symptoms as string[] || []} />
      <StringList label="Impacted Components" items={data.impacted_components as string[] || []} />
      <StringList label="Suspected Factors" items={data.suspected_factors as string[] || []} />
      <StringList label="Evidence" items={data.evidence as string[] || []} />
    </div>
  )
}

function RootCauseRenderer({ data }: { data: Record<string, unknown> }) {
  return (
    <div>
      {data.confidence && (
        <span className="artifact-confidence">Confidence: {String(data.confidence)}</span>
      )}
      {data.root_cause && <p>{String(data.root_cause)}</p>}
      <StringList label="Reasoning" items={data.reasoning as string[] || []} />
      <StringList label="Mitigations" items={data.mitigations as string[] || []} />
    </div>
  )
}

function SummaryRenderer({ data }: { data: Record<string, unknown> }) {
  return (
    <div>
      {data.title && <p><strong>{String(data.title)}</strong></p>}
      {data.summary && <p>{String(data.summary)}</p>}
      <StringList label="Key Points" items={data.key_points as string[] || []} />
      <StringList label="Decisions" items={data.decisions as string[] || []} />
      <StringList label="Risks" items={data.risks as string[] || []} />
      <StringList label="Open Questions" items={data.open_questions as string[] || []} />
    </div>
  )
}

type ActionItem = {
  title?: string
  owner?: string
  due_date?: string
  status?: string
  notes?: string
}

function ActionItemsRenderer({ data }: { data: ActionItem[] }) {
  if (!Array.isArray(data) || data.length === 0) return <p>No action items found.</p>
  return (
    <table>
      <thead>
        <tr>
          <th>Title</th>
          <th>Owner</th>
          <th>Due Date</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {data.map((item, i) => (
          <tr key={i}>
            <td>{item.title || '-'}</td>
            <td>{item.owner || '-'}</td>
            <td>{item.due_date || '-'}</td>
            <td>{item.status || 'open'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function MarkdownRenderer({ content }: { content: string }) {
  return (
    <div className="message-markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  )
}

function DeliveryRenderer({ data, label }: { data: Record<string, unknown>; label: string }) {
  if (data.sent === true || data.posted === true) {
    const target = data.channel || data.issue_key || ''
    return <p className="artifact-delivery-ok">{label}: Sent{target ? ` to ${target}` : ''}</p>
  }
  if (data.reason === 'send_to_teams_disabled' || data.reason === 'post_to_jira_disabled') {
    return <p className="artifact-delivery-skip">{label}: Skipped (disabled)</p>
  }
  if (data.sent === false || data.posted === false) {
    return <p className="artifact-delivery-skip">{label}: Skipped</p>
  }
  return <p>{label}: {JSON.stringify(data)}</p>
}

function renderContent(artifact: ArtifactEvent) {
  const { artifact_key, artifact: data } = artifact

  switch (artifact_key) {
    case 'analysis':
      return <AnalysisRenderer data={data as Record<string, unknown>} />
    case 'root_cause':
      return <RootCauseRenderer data={data as Record<string, unknown>} />
    case 'summary':
      return <SummaryRenderer data={data as Record<string, unknown>} />
    case 'action_items':
      return <ActionItemsRenderer data={data as ActionItem[]} />
    case 'memo':
    case 'jira_comment':
      return <MarkdownRenderer content={String(data)} />
    case 'jira_delivery':
      return <DeliveryRenderer data={data as Record<string, unknown>} label="Jira" />
    case 'teams_delivery':
      return <DeliveryRenderer data={data as Record<string, unknown>} label="Teams" />
    case 'memory_record':
      return <p>Memory saved successfully.</p>
    default:
      return <pre>{JSON.stringify(data, null, 2)}</pre>
  }
}

export function shouldShowArtifact(artifact: ArtifactEvent): boolean {
  if (artifact.artifact_key === 'memory_record') return false
  if (artifact.step_status === 'failed') return true
  if (artifact.artifact == null) return false
  return true
}

export function ArtifactCard({ artifact }: ArtifactCardProps) {
  const [expanded, setExpanded] = useState(true)
  const title = ARTIFACT_TITLES[artifact.artifact_key] || artifact.step_name
  const icon = ARTIFACT_ICONS[artifact.artifact_key] || '\u{1F4E6}'

  return (
    <div className="artifact-card">
      <button className="artifact-header" onClick={() => setExpanded(!expanded)} type="button">
        <span className="artifact-icon">{icon}</span>
        <span className="artifact-title">{title}</span>
        <span className={getBadgeClass(artifact.step_status)}>{artifact.step_status}</span>
        <span className="artifact-chevron">{expanded ? '▴' : '▾'}</span>
      </button>
      {expanded && (
        <div className="artifact-body">
          {renderContent(artifact)}
        </div>
      )}
    </div>
  )
}
