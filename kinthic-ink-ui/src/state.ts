// ─────────────────────────────────────────────────────────────────────────────
// src/state.ts — Pure reducer for App state (unit-testable without Ink)
// ─────────────────────────────────────────────────────────────────────────────

import type {
  ActiveGoal,
  ApprovalRequest,
  CostSummary,
  HeaderMetadata,
  IncomingMessage,
  MemoryWriteEvent,
  TelemetryData,
  ToolAuthRequest,
  TurnEventData,
  TurnPhase,
  WorkerEventData,
} from './types.js';

export type InputMode = 'prompt' | 'thinking' | 'auth' | 'done';

export type ThinkingPhase =
  | { phase: 'idle' }
  | { phase: 'thinking'; status: string; detail?: string }
  | { phase: 'done' };

export interface HistoryEntry {
  id: string;
  role: 'user' | 'assistant';
  text: string;
}

export type LedgerItem =
  | { id: string; kind: 'user'; text: string }
  | { id: string; kind: 'assistant'; text: string }
  | { id: string; kind: 'thinking'; status: string; detail?: string; turnPhase?: TurnPhase }
  | { id: string; kind: 'worker'; data: WorkerEventData }
  | { id: string; kind: 'memory'; data: MemoryWriteEvent }
  | { id: string; kind: 'tool_auth'; data: ToolAuthRequest }
  | { id: string; kind: 'approval'; data: ApprovalRequest }
  | { id: string; kind: 'approval_result'; data: ApprovalRequest; approved: boolean }
  | { id: string; kind: 'error'; message: string }
  | { id: string; kind: 'telemetry'; data: TelemetryData; workersUsed: number };

export type LedgerItemInput =
  | { kind: 'user'; text: string }
  | { kind: 'assistant'; text: string }
  | { kind: 'thinking'; status: string; detail?: string; turnPhase?: TurnPhase }
  | { kind: 'worker'; data: WorkerEventData }
  | { kind: 'memory'; data: MemoryWriteEvent }
  | { kind: 'tool_auth'; data: ToolAuthRequest }
  | { kind: 'approval'; data: ApprovalRequest }
  | { kind: 'approval_result'; data: ApprovalRequest; approved: boolean }
  | { kind: 'error'; message: string }
  | { kind: 'telemetry'; data: TelemetryData; workersUsed: number };

export interface AppState {
  header:           HeaderMetadata;
  thinking:         ThinkingPhase;
  toolAuth:         ToolAuthRequest | null;
  telemetry:        TelemetryData   | null;
  workers:          WorkerEventData[];
  activeGoal:       ActiveGoal      | null;
  approvalQueue:    ApprovalRequest[];
  cost:             CostSummary;
  memoryEvents:     MemoryWriteEvent[];
  lastError:        string | null;
  mode:             InputMode;
  history:          HistoryEntry[];
  commands:         Array<{ cmd: string; args: string; desc: string }>;
  turnCounter:      number;
  /** Shell input history loaded from ~/.kinthic/history, newest-last. */
  inputHistory:     string[];
  /** Text currently being streamed (typewriter animation); null when idle. */
  streamingText:    string | null;
  /** Chronological activity stream for the ledger UI. */
  ledger:           LedgerItem[];
  /** Canonical turn events from Python TurnEmitter (source of truth when present). */
  turnEvents:       TurnEventData[];
}

export const DEFAULT_HEADER: HeaderMetadata = {
  platform: 'OpenYF (λ) Enterprise',
  core: 'SILEX Reasoning Engine',
  version: '1.0.0',
  skillCount: 18,
  storageMode: 'SQLite + ChromaDB',
  cwd: '~',
};

export const INITIAL_STATE: AppState = {
  header:        DEFAULT_HEADER,
  thinking:      { phase: 'idle' },
  toolAuth:      null,
  telemetry:     null,
  workers:       [],
  activeGoal:    null,
  approvalQueue: [],
  cost:          { total_cost_usd: 0, total_tokens: 0, turns: 0 },
  memoryEvents:  [],
  lastError:     null,
  mode:          'prompt',
  history:       [],
  commands:      [],
  turnCounter:   0,
  inputHistory:  [],
  streamingText: null,
  ledger:        [],
  turnEvents:    [],
};

/** Max conversation entries kept in the rendered tree. */
export const MAX_HISTORY = 30;

/** Max ledger rows kept in the rendered stream. */
export const MAX_LEDGER = 120;


let _historyIdSeq = 0;
let _ledgerIdSeq = 0;

export function nextHistoryId(): string {
  _historyIdSeq += 1;
  return `h-${_historyIdSeq}`;
}

export function nextLedgerId(): string {
  _ledgerIdSeq += 1;
  return `l-${_ledgerIdSeq}`;
}

/** Reset id sequence — for tests only. */
export function resetHistoryIdSeq(): void {
  _historyIdSeq = 0;
  _ledgerIdSeq = 0;
}

export function appendLedger(
  ledger: LedgerItem[],
  item: LedgerItemInput,
): LedgerItem[] {
  return [
    ...ledger,
    { ...item, id: nextLedgerId() } as LedgerItem,
  ].slice(-MAX_LEDGER);
}

/**
 * Prepare ledger rows for display:
 * - Per-turn segments: hide thinking once assistant exists or stream is active on last turn.
 * - Defer memory and telemetry until after assistant within each turn.
 * - Keep only the last telemetry row per turn segment.
 */
export function prepareDisplayLedger(
  ledger: LedgerItem[],
  streamingText?: string | null,
): LedgerItem[] {
  const streamingActive = Boolean(streamingText && streamingText.length > 0);

  const segments: LedgerItem[][] = [];
  let current: LedgerItem[] = [];

  for (const item of ledger) {
    if (item.kind === 'user') {
      if (current.length > 0) {
        segments.push(current);
      }
      current = [item];
    } else {
      current.push(item);
    }
  }
  if (current.length > 0) {
    segments.push(current);
  }

  const result: LedgerItem[] = [];

  for (let si = 0; si < segments.length; si++) {
    const seg = segments[si];
    const isLastSegment = si === segments.length - 1;
    const user = seg[0];
    const rest = seg.slice(1);
    const hasAssistant = rest.some(item => item.kind === 'assistant');
    const hideThinking = hasAssistant || (isLastSegment && streamingActive);

    const lastTelemetry = rest.filter(item => item.kind === 'telemetry').at(-1);
    const out: LedgerItem[] = [user];
    const pendingMemory: LedgerItem[] = [];
    let pendingTelemetry: LedgerItem | null = null;

    for (const item of rest) {
      if (item.kind === 'thinking' && hideThinking) {
        continue;
      }
      if (item.kind === 'memory') {
        pendingMemory.push(item);
        continue;
      }
      if (item.kind === 'telemetry') {
        if (item === lastTelemetry) {
          pendingTelemetry = item;
        }
        continue;
      }
      out.push(item);
      if (item.kind === 'assistant') {
        out.push(...pendingMemory);
        pendingMemory.length = 0;
        if (pendingTelemetry) {
          out.push(pendingTelemetry);
          pendingTelemetry = null;
        }
      }
    }

    if (hasAssistant && pendingTelemetry) {
      out.push(pendingTelemetry);
    } else if (pendingTelemetry && !hasAssistant && !isLastSegment) {
      out.push(pendingTelemetry);
    }

    result.push(...out);
  }

  return result;
}

/** Max turn events retained before projection. */
export const MAX_TURN_EVENTS = 240;

export function appendTurnEvent(
  events: TurnEventData[],
  evt: TurnEventData,
): TurnEventData[] {
  const key = `${evt.turn_id}:${evt.seq}`;
  if (events.some(e => `${e.turn_id}:${e.seq}` === key)) {
    return events;
  }
  if (
    evt.phase === 'user'
    && events.some(e => e.phase === 'user' && e.detail === evt.detail)
  ) {
    return events;
  }
  return [...events, evt].slice(-MAX_TURN_EVENTS);
}

export function deriveApprovalQueue(events: TurnEventData[]): ApprovalRequest[] {
  const queue: ApprovalRequest[] = [];
  const resolved = new Set<string>();

  for (const evt of events) {
    if (evt.phase !== 'approval') continue;
    const p = evt.payload ?? {};
    const id = String(p.approval_id ?? '');
    if (!id) continue;
    if (p.resolved) {
      resolved.add(id);
      continue;
    }
    queue.push({
      approval_id: id,
      tool_name: String(p.tool_name ?? evt.title),
      risk_level: String(p.risk_level ?? 'unknown'),
      reason: String(p.reason ?? evt.detail ?? ''),
      arguments_preview: (p.arguments_preview as Record<string, unknown>) ?? {},
      requested_at: Number(p.requested_at ?? 0),
    });
  }

  return queue.filter(a => !resolved.has(a.approval_id)).slice(-10);
}

export function deriveWorkers(events: TurnEventData[]): WorkerEventData[] {
  const byId = new Map<string, WorkerEventData>();

  for (const evt of events) {
    if (evt.phase !== 'subagent') continue;
    const p = evt.payload ?? {};
    const workerId = String(p.worker_id ?? '');
    if (!workerId) continue;
    byId.set(workerId, {
      worker_id: workerId,
      lifecycle: String(p.lifecycle ?? 'running'),
      objective: String(p.objective ?? evt.detail ?? ''),
      worker_class: String(p.worker_class ?? 'worker'),
      detail: String(p.detail ?? ''),
      parent_id: (p.parent_id as string | null | undefined) ?? null,
      ancestry_chain: (p.ancestry_chain as string[]) ?? [],
      exit_code: p.exit_code as number | null | undefined,
      turns_used: p.turns_used as number | undefined,
      tokens_used: p.tokens_used as number | undefined,
      event_id: String(p.event_id ?? `evt_${evt.seq}`),
      timestamp: p.timestamp as number | undefined,
    });
  }

  return [...byId.values()].slice(-20);
}

/**
 * Project canonical turn events into ledger rows for ActivityLedger.
 * In-progress phases (routing/context/tool/response) feed ThinkingSpinner via
 * applyTurnEventSideEffects — not appended as ledger rows.
 */
export function projectTurnEvents(
  events: TurnEventData[],
  streamingText?: string | null,
): LedgerItem[] {
  const workerIds = new Set<string>();
  const items: LedgerItem[] = [];
  const streamingActive = Boolean(streamingText && streamingText.length > 0);

  const lastSummaryByTurn = new Map<string, TurnEventData>();
  for (const evt of events) {
    if (evt.phase === 'summary') {
      lastSummaryByTurn.set(evt.turn_id, evt);
    }
  }

  for (const evt of events) {
    const p = evt.payload ?? {};
    const id = `te-${evt.turn_id}-${evt.seq}`;

    switch (evt.phase) {
      case 'user':
        items.push({
          id,
          kind: 'user',
          text: evt.detail || String(p.text ?? ''),
        });
        break;

      case 'routing':
      case 'context':
      case 'tool':
        break;

      case 'response':
        if (evt.title === 'Kinthic') {
          const text = String(p.text ?? evt.detail ?? '');
          if (text && !streamingActive) {
            items.push({ id, kind: 'assistant', text });
          }
        }
        break;

      case 'subagent': {
        const workerId = String(p.worker_id ?? '');
        if (workerId) workerIds.add(workerId);
        items.push({
          id,
          kind: 'worker',
          data: {
            worker_id: workerId,
            lifecycle: String(p.lifecycle ?? 'running'),
            objective: String(p.objective ?? evt.detail ?? ''),
            worker_class: String(p.worker_class ?? 'worker'),
            detail: String(p.detail ?? ''),
            parent_id: (p.parent_id as string | null | undefined) ?? null,
            ancestry_chain: (p.ancestry_chain as string[]) ?? [],
            exit_code: p.exit_code as number | null | undefined,
            turns_used: p.turns_used as number | undefined,
            tokens_used: p.tokens_used as number | undefined,
            event_id: String(p.event_id ?? `evt_${evt.seq}`),
            timestamp: p.timestamp as number | undefined,
          },
        });
        break;
      }

      case 'approval':
        if (p.resolved) {
          items.push({
            id,
            kind: 'approval_result',
            data: {
              approval_id: String(p.approval_id ?? ''),
              tool_name: String(p.tool_name ?? evt.title),
              risk_level: String(p.risk_level ?? 'unknown'),
              reason: String(p.reason ?? ''),
              requested_at: Number(p.requested_at ?? 0),
            },
            approved: Boolean(p.approved),
          });
        }
        break;

      case 'memory':
        items.push({
          id,
          kind: 'memory',
          data: {
            count: Number(p.count ?? 0),
            items: (p.items as string[]) ?? [],
          },
        });
        break;

      case 'error':
        items.push({
          id,
          kind: 'error',
          message: evt.detail || evt.title,
        });
        break;

      case 'summary': {
        if (lastSummaryByTurn.get(evt.turn_id) !== evt) {
          break;
        }
        items.push({
          id,
          kind: 'telemetry',
          data: {
            latencyMs: Number(p.latencyMs ?? 0),
            tokens: Number(p.tokens ?? 0),
            memoriesWritten: Number(p.memoriesWritten ?? 0),
            toolsExecuted: Number(p.toolsExecuted ?? 0),
          },
          workersUsed: Number(p.workersUsed ?? workerIds.size),
        });
        break;
      }

      default:
        break;
    }
  }

  return items.slice(-MAX_LEDGER);
}

function usesTurnEvents(state: AppState): boolean {
  return state.turnEvents.length > 0;
}

function applyTurnEventSideEffects(
  state: AppState,
  evt: TurnEventData,
): Pick<AppState, 'mode' | 'thinking' | 'telemetry' | 'lastError' | 'memoryEvents'> {
  const p = evt.payload ?? {};
  let mode = state.mode;
  let thinking = state.thinking;
  let telemetry = state.telemetry;
  let lastError = state.lastError;
  let memoryEvents = state.memoryEvents;

  switch (evt.phase) {
    case 'routing':
    case 'context':
    case 'tool':
      mode = 'thinking';
      thinking = { phase: 'thinking', status: evt.title, detail: evt.detail };
      telemetry = null;
      lastError = null;
      break;
    case 'response':
      if (evt.title === 'Kinthic') {
        thinking = { phase: 'done' };
        mode = 'prompt';
      } else {
        mode = 'thinking';
        thinking = { phase: 'thinking', status: evt.title, detail: evt.detail };
      }
      break;
    case 'approval':
      if (!p.resolved) {
        telemetry = null;
        lastError = null;
      }
      break;
    case 'memory':
      memoryEvents = [
        ...memoryEvents,
        {
          count: Number(p.count ?? 0),
          items: (p.items as string[]) ?? [],
        },
      ].slice(-5);
      break;
    case 'error':
      mode = 'prompt';
      thinking = { phase: 'done' };
      lastError = evt.detail || evt.title;
      break;
    case 'summary':
      thinking = { phase: 'done' };
      telemetry = {
        latencyMs: Number(p.latencyMs ?? 0),
        tokens: Number(p.tokens ?? 0),
        memoriesWritten: Number(p.memoriesWritten ?? 0),
        toolsExecuted: Number(p.toolsExecuted ?? 0),
      };
      break;
    default:
      break;
  }

  return { mode, thinking, telemetry, lastError, memoryEvents };
}

export function appendHistory(
  history: HistoryEntry[],
  role: 'user' | 'assistant',
  text: string,
): HistoryEntry[] {
  return [
    ...history,
    { id: nextHistoryId(), role, text },
  ].slice(-MAX_HISTORY);
}

export function reduceAppState(state: AppState, msg: IncomingMessage): AppState {
  switch (msg.type) {
    case 'turn_event': {
      const turnEvents = appendTurnEvent(state.turnEvents, msg.data);
      const side = applyTurnEventSideEffects(state, msg.data);
      return {
        ...state,
        ...side,
        turnEvents,
        approvalQueue: deriveApprovalQueue(turnEvents),
        workers: deriveWorkers(turnEvents),
        ledger: projectTurnEvents(turnEvents, state.streamingText),
      };
    }

    case 'header':
      return { ...state, header: msg.data };

    case 'thinking':
      return {
        ...state,
        mode: 'thinking',
        thinking: { phase: 'thinking', status: msg.data.status, detail: msg.data.detail },
        telemetry: null,
        lastError: null,
        ledger: usesTurnEvents(state)
          ? state.ledger
          : appendLedger(state.ledger, {
              kind: 'thinking',
              status: msg.data.status,
              detail: msg.data.detail,
            }),
      };

    case 'tool_auth':
      return {
        ...state,
        mode: 'auth',
        thinking: { phase: 'done' },
        toolAuth: msg.data,
        ledger: usesTurnEvents(state)
          ? state.ledger
          : appendLedger(state.ledger, { kind: 'tool_auth', data: msg.data }),
      };

    case 'telemetry': {
      const workersUsed = new Set(state.workers.map(w => w.worker_id)).size;
      return {
        ...state,
        thinking: { phase: 'done' },
        telemetry: msg.data,
        ledger: usesTurnEvents(state)
          ? state.ledger
          : appendLedger(state.ledger, {
              kind: 'telemetry',
              data: msg.data,
              workersUsed,
            }),
      };
    }

    case 'response': {
      const text = msg.data?.text ?? '';
      return {
        ...state,
        mode: 'prompt',
        thinking: { phase: 'done' },
        streamingText: null,
        history: appendHistory(state.history, 'assistant', text),
        ledger: usesTurnEvents(state)
          ? projectTurnEvents(state.turnEvents, null)
          : appendLedger(state.ledger, { kind: 'assistant', text }),
      };
    }

    case 'stream': {
      const text = msg.data?.text ?? '';
      return {
        ...state,
        mode: 'prompt',
        thinking: { phase: 'done' },
        streamingText: text,
        ledger: usesTurnEvents(state)
          ? projectTurnEvents(state.turnEvents, text)
          : state.ledger,
      };
    }

    case 'history_update':
      return { ...state, inputHistory: msg.data.history ?? [] };

    case 'error':
      return {
        ...state,
        mode: 'prompt',
        thinking: { phase: 'done' },
        toolAuth: null,
        streamingText: null,
        lastError: msg.data.message,
        ledger: usesTurnEvents(state)
          ? state.ledger
          : appendLedger(state.ledger, { kind: 'error', message: msg.data.message }),
      };

    case 'cancel':
      return {
        ...state,
        mode: 'prompt',
        thinking: { phase: 'done' },
        toolAuth: null,
        streamingText: null,
      };

    case 'auth_complete':
      return {
        ...state,
        mode: 'thinking',
        toolAuth: null,
        thinking: { phase: 'thinking', status: 'Resuming...' },
      };

    case 'worker': {
      const idx = state.workers.findIndex(w => w.worker_id === msg.data.worker_id);
      const workers = [...state.workers];
      if (idx >= 0) {
        workers[idx] = { ...workers[idx], ...msg.data };
      } else {
        workers.push(msg.data);
      }
      return {
        ...state,
        workers: usesTurnEvents(state) ? state.workers : workers.slice(-20),
        ledger: usesTurnEvents(state)
          ? state.ledger
          : appendLedger(state.ledger, { kind: 'worker', data: msg.data }),
      };
    }

    case 'active_goal':
      return { ...state, activeGoal: msg.data };

    case 'approval_requested':
      return usesTurnEvents(state)
        ? state
        : {
            ...state,
            approvalQueue: [
              ...state.approvalQueue.filter(a => a.approval_id !== msg.data.approval_id),
              msg.data,
            ].slice(-10),
          };

    case 'approval_resolved': {
      const resolved = state.approvalQueue.find(
        a => a.approval_id === msg.data.approval_id,
      );
      return {
        ...state,
        approvalQueue: state.approvalQueue.filter(
          a => a.approval_id !== msg.data.approval_id,
        ),
        ledger: usesTurnEvents(state) || !resolved
          ? state.ledger
          : appendLedger(state.ledger, {
              kind: 'approval_result',
              data: resolved,
              approved: msg.data.approved,
            }),
      };
    }

    case 'cost_update':
      return { ...state, cost: msg.data };

    case 'memory_write':
      return {
        ...state,
        memoryEvents: [...state.memoryEvents, msg.data].slice(-5),
        ledger: usesTurnEvents(state)
          ? state.ledger
          : appendLedger(state.ledger, { kind: 'memory', data: msg.data }),
      };

    case 'init_commands':
      return { ...state, commands: msg.data.commands ?? [] };

    case 'user_echo':
      return reduceUserSubmit(state, msg.data.text);

    case 'done':
      return { ...state, mode: 'done' };

    default:
      return state;
  }
}

export function reduceUserSubmit(state: AppState, text: string): AppState {
  return {
    ...state,
    mode: 'thinking',
    thinking: { phase: 'thinking', status: 'Working...', detail: 'Starting turn' },
    telemetry: null,
    workers: [],
    memoryEvents: [],
    lastError: null,
    history: appendHistory(state.history, 'user', text),
    ledger: appendLedger(state.ledger, { kind: 'user', text }),
    turnCounter: state.turnCounter + 1,
  };
}

export function reduceAuthDecision(
  state: AppState,
  approved: boolean,
): AppState {
  if (approved) {
    return {
      ...state,
      mode: 'thinking',
      toolAuth: null,
      thinking: { phase: 'thinking', status: 'Executing approved change...' },
    };
  }
  return {
    ...state,
    mode: 'prompt',
    toolAuth: null,
    thinking: { phase: 'done' },
  };
}

