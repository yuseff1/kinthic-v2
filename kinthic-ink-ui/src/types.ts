// ─────────────────────────────────────────────────────────────────────────────
// src/types.ts — Shared TypeScript interfaces for all Kinthic Ink components.
// ─────────────────────────────────────────────────────────────────────────────

/** Metadata injected into the identity header at startup. */
export interface HeaderMetadata {
  platform: string;        // e.g. "OpenYF (λ) Enterprise"
  core: string;            // e.g. "SILEX Reasoning Engine"
  version: string;         // e.g. "1.0.0"
  skillCount: number;      // e.g. 18
  storageMode: string;     // e.g. "SQLite + ChromaDB"
  cwd: string;             // e.g. "/home/user/project"
}

/** A single line in a tool diff summary. */
export interface DiffLine {
  type: 'add' | 'remove' | 'context';
  content: string;
}

/** Full descriptor of a tool authorization request fired by the model. */
export interface ToolAuthRequest {
  toolName: string;        // e.g. "code_editor.propose_edit"
  targetPath: string;      // e.g. "./silex/tools/system.py"
  operationType: string;   // e.g. "local file alteration"
  diffLines: DiffLine[];
  txId?: string;           // transaction ID returned on approval
}

/** Telemetry packet written to the footer bar after execution. */
export interface TelemetryData {
  latencyMs: number;
  tokens: number;
  memoriesWritten: number;
  toolsExecuted: number;
}

/** Worker lifecycle event from orchestration telemetry. */
export interface WorkerEventData {
  worker_id: string;
  lifecycle: 'pending' | 'running' | 'done' | 'failed' | 'killed' | string;
  objective?: string;
  parent_id?: string | null;
  ancestry_chain?: string[];
  worker_class?: 'structural_executor' | 'cognitive_worker' | string;
  detail?: string;
  exit_code?: number | null;
  turns_used?: number;
  tokens_used?: number;
  timestamp?: number;
  event_id: string;
}

/** Pending approval request for a risky tool call. */
export interface ApprovalRequest {
  approval_id: string;
  tool_name: string;
  risk_level: string;
  reason: string;
  arguments_preview?: Record<string, unknown>;
  requested_at: number;
}

/** Active goal being executed in the background. */
export interface ActiveGoal {
  goal_id: string;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | string;
  run_id?: string;
  started_at?: number;
  last_heartbeat?: number;
}

/** Accumulated cost and usage metrics for the operator dashboard. */
export interface CostSummary {
  total_cost_usd: number;
  total_tokens: number;
  turns: number;
  model?: string;
}

/** Memory write/update event emitted after a turn. */
export interface MemoryWriteEvent {
  count: number;
  items?: string[];
}

/** Canonical turn visibility event from Python TurnEmitter. */
export type TurnPhase =
  | 'user'
  | 'routing'
  | 'context'
  | 'tool'
  | 'subagent'
  | 'approval'
  | 'response'
  | 'memory'
  | 'error'
  | 'summary';

export interface TurnEventData {
  turn_id: string;
  seq: number;
  phase: TurnPhase;
  title: string;
  detail?: string;
  payload?: Record<string, unknown>;
}

// ─────────────────────────────────────────────────────────────────────────────
// JSON message envelope received on stdin. Each line is one of these.
// ─────────────────────────────────────────────────────────────────────────────
export type IncomingMessage =
  | { type: 'header';             data: HeaderMetadata }
  | { type: 'thinking';           data: { status: string; detail?: string } }
  | { type: 'tool_auth';          data: ToolAuthRequest }
  | { type: 'approval_requested'; data: ApprovalRequest }
  | { type: 'approval_resolved';  data: { approval_id: string; approved: boolean } }
  | { type: 'telemetry';          data: TelemetryData }
  | { type: 'worker';             data: WorkerEventData }
  | { type: 'active_goal';        data: ActiveGoal }
  | { type: 'cost_update';        data: CostSummary }
  | { type: 'memory_write';       data: MemoryWriteEvent }
  | { type: 'response';           data: { text: string } }
  | { type: 'stream';             data: { text: string } }
  | { type: 'history_update';     data: { history: string[] } }
  | { type: 'error';              data: { message: string } }
  | { type: 'cancel';             data?: { message?: string } }
  | { type: 'auth_complete';      data?: Record<string, never> }
  | { type: 'init_commands';      data: { commands: Array<{ cmd: string; args: string; desc: string }> } }
  | { type: 'user_echo';           data: { text: string } }
  | { type: 'turn_event';          data: TurnEventData }
  | { type: 'done' };

