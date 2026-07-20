// ─────────────────────────────────────────────────────────────────────────────
// src/state.test.ts — Reducer regression tests (no Ink render required)
// ─────────────────────────────────────────────────────────────────────────────

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  INITIAL_STATE,
  appendHistory,
  appendLedger,
  reduceAppState,
  reduceUserSubmit,
  reduceAuthDecision,

  resetHistoryIdSeq,
  prepareDisplayLedger,
  projectTurnEvents,
  deriveApprovalQueue,
  MAX_HISTORY,

  MAX_LEDGER,
} from './state.js';

describe('projectTurnEvents', () => {
  it('projects golden-path turn events into ledger order', () => {
    const turnId = 'turn_test';
    const events = [
      { turn_id: turnId, seq: 1, phase: 'user' as const, title: 'You', detail: 'hello' },
      { turn_id: turnId, seq: 2, phase: 'routing' as const, title: 'routing', detail: 'fast path' },
      { turn_id: turnId, seq: 3, phase: 'tool' as const, title: 'spawn_worker', detail: 'planned' },
      {
        turn_id: turnId,
        seq: 4,
        phase: 'approval' as const,
        title: 'spawn_worker',
        detail: 'needs approval',
        payload: {
          approval_id: 'a1',
          tool_name: 'spawn_worker',
          risk_level: 'sandbox_write',
          reason: 'needs approval',
          resolved: true,
          approved: true,
        },
      },
      {
        turn_id: turnId,
        seq: 5,
        phase: 'subagent' as const,
        title: 'cognitive_worker',
        detail: 'running',
        payload: {
          worker_id: 'w1',
          lifecycle: 'running',
          worker_class: 'cognitive_worker',
          event_id: 'e1',
        },
      },
      {
        turn_id: turnId,
        seq: 6,
        phase: 'response' as const,
        title: 'Kinthic',
        detail: 'Done.',
        payload: { text: 'Done.' },
      },
      {
        turn_id: turnId,
        seq: 7,
        phase: 'summary' as const,
        title: 'summary',
        detail: '1s',
        payload: {
          latencyMs: 1000,
          tokens: 100,
          memoriesWritten: 0,
          toolsExecuted: 1,
          workersUsed: 1,
        },
      },
    ];

    const ledger = projectTurnEvents(events, null);
    const kinds = ledger.map(item => item.kind);
    assert.deepEqual(kinds, [
      'user', 'approval_result', 'worker', 'assistant', 'telemetry',
    ]);
  });

  it('keeps only the last summary per turn_id', () => {
    const turnId = 'turn_dup';
    const events = [
      { turn_id: turnId, seq: 1, phase: 'user' as const, title: 'You', detail: 'hi' },
      {
        turn_id: turnId,
        seq: 2,
        phase: 'summary' as const,
        title: 'summary',
        detail: 'old',
        payload: { latencyMs: 100, tokens: 1, memoriesWritten: 0, toolsExecuted: 0, workersUsed: 0 },
      },
      {
        turn_id: turnId,
        seq: 3,
        phase: 'summary' as const,
        title: 'summary',
        detail: 'new',
        payload: { latencyMs: 200, tokens: 2, memoriesWritten: 0, toolsExecuted: 0, workersUsed: 0 },
      },
    ];
    const ledger = projectTurnEvents(events, null);
    const telemetry = ledger.filter(item => item.kind === 'telemetry');
    assert.equal(telemetry.length, 1);
    if (telemetry[0]?.kind === 'telemetry') {
      assert.equal(telemetry[0].data.latencyMs, 200);
    }
  });

  it('hides assistant during stream and defers summary via prepareDisplayLedger', () => {
    const turnId = 'turn_stream';
    const events = [
      { turn_id: turnId, seq: 1, phase: 'user' as const, title: 'You', detail: 'hi' },
      { turn_id: turnId, seq: 2, phase: 'routing' as const, title: 'routing', detail: 'path' },
      {
        turn_id: turnId,
        seq: 3,
        phase: 'response' as const,
        title: 'Kinthic',
        detail: 'Hello',
        payload: { text: 'Hello' },
      },
      {
        turn_id: turnId,
        seq: 4,
        phase: 'summary' as const,
        title: 'summary',
        detail: '0.5s',
        payload: { latencyMs: 500, tokens: 10, memoriesWritten: 0, toolsExecuted: 0, workersUsed: 0 },
      },
    ];

    const streaming = prepareDisplayLedger(projectTurnEvents(events, 'Hel'), 'Hel');
    assert.deepEqual(streaming.map(i => i.kind), ['user']);

    const done = prepareDisplayLedger(projectTurnEvents(events, null), null);
    assert.deepEqual(done.map(i => i.kind), ['user', 'assistant', 'telemetry']);
  });

  it('defers memory until after assistant within a turn', () => {
    resetHistoryIdSeq();
    let ledger = appendLedger([], { kind: 'user', text: 'hi' });
    ledger = appendLedger(ledger, {
      kind: 'memory',
      data: { count: 1, items: ['note'] },
    });
    ledger = appendLedger(ledger, { kind: 'assistant', text: 'Hello.' });

    const display = prepareDisplayLedger(ledger, null);
    assert.deepEqual(display.map(i => i.kind), ['user', 'assistant', 'memory']);
  });

  it('dedupes telemetry to one line per turn segment', () => {
    resetHistoryIdSeq();
    let ledger = appendLedger([], { kind: 'user', text: 'a' });
    ledger = appendLedger(ledger, {
      kind: 'telemetry',
      data: { latencyMs: 100, tokens: 1, memoriesWritten: 0, toolsExecuted: 0 },
      workersUsed: 0,
    });
    ledger = appendLedger(ledger, {
      kind: 'telemetry',
      data: { latencyMs: 200, tokens: 2, memoriesWritten: 0, toolsExecuted: 0 },
      workersUsed: 0,
    });
    ledger = appendLedger(ledger, { kind: 'assistant', text: 'Done' });

    const display = prepareDisplayLedger(ledger, null);
    const telemetry = display.filter(i => i.kind === 'telemetry');
    assert.equal(telemetry.length, 1);
    if (telemetry[0]?.kind === 'telemetry') {
      assert.equal(telemetry[0].data.latencyMs, 200);
    }
  });

  it('derives approval queue from pending approval events', () => {
    const events = [
      {
        turn_id: 't1',
        seq: 1,
        phase: 'approval' as const,
        title: 'spawn_worker',
        detail: 'needs approval',
        payload: {
          approval_id: 'a1',
          tool_name: 'spawn_worker',
          risk_level: 'sandbox_write',
          reason: 'needs approval',
          requested_at: 1,
          resolved: false,
        },
      },
    ];
    const queue = deriveApprovalQueue(events);
    assert.equal(queue.length, 1);
    assert.equal(queue[0].tool_name, 'spawn_worker');
  });
});

describe('reduceAppState turn_event', () => {
  it('consumes turn_event and updates ledger projection', () => {
    let state = INITIAL_STATE;
    state = reduceAppState(state, {
      type: 'turn_event',
      data: {
        turn_id: 't1',
        seq: 1,
        phase: 'user',
        title: 'You',
        detail: 'spawn worker',
      },
    });
    assert.equal(state.turnEvents.length, 1);
    assert.equal(state.ledger.length, 1);
    assert.equal(state.ledger[0].kind, 'user');
  });
});

describe('reduceAppState', () => {
  it('returns to prompt on response', () => {
    const thinking = reduceAppState(INITIAL_STATE, {
      type: 'thinking',
      data: { status: 'Thinking...' },
    });
    assert.equal(thinking.mode, 'thinking');

    const done = reduceAppState(thinking, {
      type: 'response',
      data: { text: 'Hello' },
    });
    assert.equal(done.mode, 'prompt');
    assert.equal(done.history.length, 1);
    assert.equal(done.history[0].role, 'assistant');
    assert.equal(done.history[0].text, 'Hello');
    assert.ok(done.history[0].id.startsWith('h-'));
  });

  it('returns to prompt on error and cancel', () => {
    const thinking = reduceAppState(INITIAL_STATE, {
      type: 'thinking',
      data: { status: 'Thinking...' },
    });

    const errored = reduceAppState(thinking, {
      type: 'error',
      data: { message: 'boom' },
    });
    assert.equal(errored.mode, 'prompt');
    assert.equal(errored.thinking.phase, 'done');
    assert.equal(errored.lastError, 'boom');

    const cancelled = reduceAppState(thinking, {
      type: 'cancel',
      data: { message: 'nope' },
    });
    assert.equal(cancelled.mode, 'prompt');
  });

  it('auth_complete resumes thinking without toolAuth', () => {
    const auth = reduceAppState(INITIAL_STATE, {
      type: 'tool_auth',
      data: {
        toolName: 'code_editor',
        targetPath: 'x.py',
        operationType: 'edit',
        diffLines: [],
        txId: 'abc',
      },
    });
    assert.equal(auth.mode, 'auth');

    const resumed = reduceAppState(auth, { type: 'auth_complete' });
    assert.equal(resumed.mode, 'thinking');
    assert.equal(resumed.toolAuth, null);
  });

  it('stores memory write events for operator visibility', () => {
    let state = INITIAL_STATE;
    state = reduceAppState(state, {
      type: 'memory_write',
      data: { count: 2, items: ['a', 'b'] },
    });
    assert.equal(state.memoryEvents.length, 1);
    assert.equal(state.memoryEvents[0].count, 2);
  });

  it('stores worker lifecycle events for topology rendering', () => {
    const state = reduceAppState(INITIAL_STATE, {
      type: 'worker',
      data: {
        worker_id: 'w-1',
        lifecycle: 'running',
        objective: 'inspect repo',
        worker_class: 'cognitive_worker',
        event_id: 'e-1',
      },
    });
    assert.equal(state.workers.length, 1);
    assert.equal(state.workers[0].worker_class, 'cognitive_worker');
    assert.equal(state.ledger.length, 1);
    assert.equal(state.ledger[0].kind, 'worker');
  });

  it('builds chronological ledger entries across a turn', () => {
    resetHistoryIdSeq();
    let state = reduceUserSubmit(INITIAL_STATE, 'audit the repo');
    assert.equal(state.ledger.length, 1);
    assert.equal(state.ledger[0].kind, 'user');

    state = reduceAppState(state, {
      type: 'thinking',
      data: { status: 'Thinking...', detail: '[Fast Router] Routed to FAST path' },
    });
    assert.equal(state.ledger.at(-1)?.kind, 'thinking');

    state = reduceAppState(state, {
      type: 'worker',
      data: {
        worker_id: 'w-1',
        lifecycle: 'running',
        worker_class: 'cognitive_worker',
        event_id: 'e-1',
      },
    });
    state = reduceAppState(state, {
      type: 'memory_write',
      data: { count: 1, items: ['test memory'] },
    });
    state = reduceAppState(state, {
      type: 'telemetry',
      data: { latencyMs: 900, tokens: 500, memoriesWritten: 1, toolsExecuted: 1 },
    });
    state = reduceAppState(state, {
      type: 'response',
      data: { text: 'Done.' },
    });

    const kinds = state.ledger.map(item => item.kind);
    assert.deepEqual(kinds, [
      'user', 'thinking', 'worker', 'memory', 'telemetry', 'assistant',
    ]);
    const summary = state.ledger.find(item => item.kind === 'telemetry');
    assert.ok(summary && summary.kind === 'telemetry');
    assert.equal(summary.workersUsed, 1);
  });

  it('records approval result in ledger after resolve', () => {
    resetHistoryIdSeq();
    let state = reduceAppState(INITIAL_STATE, {
      type: 'approval_requested',
      data: {
        approval_id: 'a-1',
        tool_name: 'spawn_worker',
        risk_level: 'sandbox_write',
        reason: 'Error: Approval required for spawn_worker (risk=sandbox_write)',
        requested_at: Date.now(),
      },
    });
    assert.equal(state.approvalQueue.length, 1);
    assert.equal(state.ledger.length, 0);

    state = reduceAppState(state, {
      type: 'approval_resolved',
      data: { approval_id: 'a-1', approved: true },
    });
    assert.equal(state.approvalQueue.length, 0);
    assert.equal(state.ledger.length, 1);
    assert.equal(state.ledger[0].kind, 'approval_result');
    if (state.ledger[0].kind === 'approval_result') {
      assert.equal(state.ledger[0].approved, true);
    }
  });

  it('caps ledger at MAX_LEDGER', () => {
    resetHistoryIdSeq();
    let ledger = appendLedger([], { kind: 'user', text: '0' });
    for (let i = 1; i <= MAX_LEDGER + 5; i++) {
      ledger = appendLedger(ledger, { kind: 'thinking', status: String(i) });
    }
    assert.equal(ledger.length, MAX_LEDGER);
  });
});

describe('prepareDisplayLedger', () => {
  it('hides in-turn thinking rows once streaming starts', () => {
    resetHistoryIdSeq();
    let ledger = appendLedger([], { kind: 'user', text: 'hello' });
    ledger = appendLedger(ledger, { kind: 'thinking', status: 'Thinking...' });
    ledger = appendLedger(ledger, { kind: 'thinking', status: 'Routing', detail: 'fast path' });

    const duringThinking = prepareDisplayLedger(ledger, null);
    assert.equal(duringThinking.filter(item => item.kind === 'thinking').length, 2);

    const whileStreaming = prepareDisplayLedger(ledger, 'Hello there');
    assert.equal(whileStreaming.filter(item => item.kind === 'thinking').length, 0);
    assert.equal(whileStreaming.at(-1)?.kind, 'user');
  });

  it('places telemetry summary after the assistant reply', () => {
    resetHistoryIdSeq();
    let ledger = appendLedger([], { kind: 'user', text: 'hello' });
    ledger = appendLedger(ledger, { kind: 'thinking', status: 'Thinking...' });
    ledger = appendLedger(ledger, {
      kind: 'telemetry',
      data: { latencyMs: 1200, tokens: 100, memoriesWritten: 1, toolsExecuted: 0 },
      workersUsed: 0,
    });
    ledger = appendLedger(ledger, { kind: 'memory', data: { count: 1, items: ['note'] } });
    ledger = appendLedger(ledger, { kind: 'assistant', text: 'Hi.' });

    const display = prepareDisplayLedger(ledger, null);
    const kinds = display.map(item => item.kind);
    assert.deepEqual(kinds, ['user', 'assistant', 'memory', 'telemetry']);
  });

  it('holds telemetry back until the assistant reply finishes streaming', () => {
    resetHistoryIdSeq();
    let ledger = appendLedger([], { kind: 'user', text: 'hello' });
    ledger = appendLedger(ledger, {
      kind: 'telemetry',
      data: { latencyMs: 900, tokens: 50, memoriesWritten: 0, toolsExecuted: 0 },
      workersUsed: 0,
    });

    const whileStreaming = prepareDisplayLedger(ledger, 'Partial');
    assert.deepEqual(whileStreaming.map(item => item.kind), ['user']);

    ledger = appendLedger(ledger, { kind: 'assistant', text: 'Partial response' });
    const afterResponse = prepareDisplayLedger(ledger, null);
    assert.deepEqual(afterResponse.map(item => item.kind), ['user', 'assistant', 'telemetry']);
  });
});

describe('history stability', () => {
  it('uses stable ids across appendHistory', () => {
    resetHistoryIdSeq();
    const h1 = appendHistory([], 'user', 'one');
    const h2 = appendHistory(h1, 'assistant', 'two');
    assert.notEqual(h1[0].id, h2[1].id);
    assert.equal(h2.length, 2);
  });

  it('caps history at MAX_HISTORY', () => {
    resetHistoryIdSeq();
    let history = appendHistory([], 'user', '0');
    for (let i = 1; i <= MAX_HISTORY + 5; i++) {
      history = appendHistory(history, 'user', String(i));
    }
    assert.equal(history.length, MAX_HISTORY);
  });
});

describe('reduceUserSubmit', () => {
  it('increments turnCounter and sets working state on submit', () => {
    resetHistoryIdSeq();
    const next = reduceUserSubmit(INITIAL_STATE, 'hello');
    assert.equal(next.mode, 'thinking');
    assert.equal(next.turnCounter, 1);
    assert.equal(next.thinking.phase, 'thinking');
    if (next.thinking.phase === 'thinking') {
      assert.equal(next.thinking.status, 'Working...');
    }
    assert.equal(next.history.length, 1);
    assert.equal(next.history[0].text, 'hello');
  });

  it('simulates multi-turn session without remount token churn issues', () => {
    resetHistoryIdSeq();
    let state = INITIAL_STATE;

    for (let turn = 1; turn <= 6; turn++) {
      state = reduceUserSubmit(state, `prompt ${turn}`);
      state = reduceAppState(state, {
        type: 'response',
        data: { text: `reply ${turn}\nline2\nline3` },
      });
    }

    assert.equal(state.mode, 'prompt');
    assert.equal(state.turnCounter, 6);
    assert.equal(state.history.length, 12);
    const finalIds = state.history.map(h => h.id);
    assert.equal(new Set(finalIds).size, finalIds.length, 'history ids must stay unique');
  });
});

describe('reduceAuthDecision', () => {
  it('approve keeps thinking mode', () => {
    const auth = reduceAppState(INITIAL_STATE, {
      type: 'tool_auth',
      data: {
        toolName: 't',
        targetPath: 'p',
        operationType: 'op',
        diffLines: [],
      },
    });
    const approved = reduceAuthDecision(auth, true);
    assert.equal(approved.mode, 'thinking');
    assert.equal(approved.toolAuth, null);
  });

  it('reject returns to prompt', () => {
    const auth = reduceAppState(INITIAL_STATE, {
      type: 'tool_auth',
      data: {
        toolName: 't',
        targetPath: 'p',
        operationType: 'op',
        diffLines: [],
      },
    });
    const rejected = reduceAuthDecision(auth, false);
    assert.equal(rejected.mode, 'prompt');
  });
});
