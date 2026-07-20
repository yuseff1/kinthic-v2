#!/usr/bin/env node
// ─────────────────────────────────────────────────────────────────────────────
// src/index.tsx  (v4 — file-poll event bus with lifecycle cleanup)
// ─────────────────────────────────────────────────────────────────────────────

import React from 'react';
import { render } from 'ink';
import fs from 'fs';
import net from 'net';
import os from 'os';
import path from 'path';
import App from './App.js';
import type { IncomingMessage, TurnPhase } from './types.js';

const args = process.argv.slice(2);
const isDemoMode = args.includes('--demo');

const EVENTS_FILE: string = process.env['KINTHIC_EVENTS_FILE']
  ?? path.join(os.homedir(), '.kinthic', 'ink_events.ndjson');

const EVENTS_PORT: number | null = (() => {
  const raw = process.env['KINTHIC_EVENTS_PORT']?.trim();
  if (!raw) return null;
  const port = Number.parseInt(raw, 10);
  return Number.isFinite(port) && port > 0 ? port : null;
})();

let globalDispatch: ((msg: IncomingMessage) => void) | null = null;
let pollerInterval: ReturnType<typeof setInterval> | null = null;
let tcpSocket: net.Socket | null = null;
let lastDispatchedKey = '';

function registerDispatch(fn: (msg: IncomingMessage) => void): void {
  globalDispatch = fn;
  if (isDemoMode) {
    runDemoSequence();
  } else if (EVENTS_PORT !== null) {
    startTcpEventStream(EVENTS_PORT);
  } else {
    startFilePoller();
  }
}

const { waitUntilExit } = render(
  <App registerDispatch={registerDispatch} />,
  {
    stdin:        process.stdin,
    stdout:       process.stdout,
    patchConsole: true,
    exitOnCtrlC:  true,
  }
);

function stopEventReceiver(): void {
  stopFilePoller();
  if (tcpSocket !== null) {
    tcpSocket.destroy();
    tcpSocket = null;
  }
}

function dispatchIncomingLine(trimmed: string): void {
  if (!trimmed) return;
  try {
    const msg = JSON.parse(trimmed) as IncomingMessage;

    if (msg.type === 'thinking') {
      const d = msg.data as { status?: string; detail?: string };
      const key = `thinking:${d?.status ?? ''}:${d?.detail ?? ''}`;
      if (key === lastDispatchedKey) return;
      lastDispatchedKey = key;
    } else if (msg.type === 'turn_event') {
      const d = msg.data;
      const key = `turn_event:${d.turn_id}:${d.seq}`;
      if (key === lastDispatchedKey) return;
      lastDispatchedKey = key;
    } else {
      lastDispatchedKey = '';
    }

    globalDispatch?.(msg);
  } catch {
    // Skip malformed lines
  }
}

function startTcpEventStream(port: number): void {
  let lineBuffer = '';

  const connect = (): void => {
    const socket = net.createConnection({ host: '127.0.0.1', port }, () => {
      tcpSocket = socket;
    });

    socket.setEncoding('utf8');
    socket.on('data', (chunk: string) => {
      lineBuffer += chunk;
      const lines = lineBuffer.split('\n');
      lineBuffer = lines.pop() ?? '';
      for (const line of lines) {
        dispatchIncomingLine(line.trim());
      }
    });
    socket.on('close', () => {
      if (tcpSocket === socket) {
        tcpSocket = null;
      }
      setTimeout(connect, 100);
    });
    socket.on('error', () => {
      socket.destroy();
    });
  };

  connect();
}

function stopFilePoller(): void {
  if (pollerInterval !== null) {
    clearInterval(pollerInterval);
    pollerInterval = null;
  }
}

function startFilePoller(): void {
  let fileOffset = 0;
  let lineBuffer = '';

  try {
    if (fs.existsSync(EVENTS_FILE)) {
      fileOffset = 0;
    }
  } catch {
    fileOffset = 0;
  }

  const poll = (): void => {
    try {
      const stat = fs.statSync(EVENTS_FILE, { throwIfNoEntry: false });
      if (!stat) return;

      if (stat.size < fileOffset) {
        fileOffset = 0;
        lineBuffer = '';
        lastDispatchedKey = '';
      }

      if (stat.size <= fileOffset) return;

      const toRead = stat.size - fileOffset;
      const buf = Buffer.alloc(toRead);
      const fd = fs.openSync(EVENTS_FILE, 'r');
      fs.readSync(fd, buf, 0, toRead, fileOffset);
      fs.closeSync(fd);
      fileOffset = stat.size;

      lineBuffer += buf.toString('utf8');
      const lines = lineBuffer.split('\n');
      lineBuffer = lines.pop() ?? '';

      for (const line of lines) {
        dispatchIncomingLine(line.trim());
      }
    } catch {
      // File not yet created — retry next tick
    }
  };

  pollerInterval = setInterval(poll, 50);
}

function runDemoSequence(): void {
  const send = (msg: IncomingMessage, delayMs: number): void => {
    setTimeout(() => globalDispatch?.(msg), delayMs);
  };

  const turnId = 'turn_demo_001';
  let seq = 0;
  const te = (
    phase: TurnPhase,
    title: string,
    detail: string,
    payload: Record<string, unknown> = {},
    delayMs: number,
  ): void => {
    seq += 1;
    send({
      type: 'turn_event',
      data: {
        turn_id: turnId,
        seq,
        phase,
        title,
        detail,
        payload,
      },
    }, delayMs);
  };

  function fireCompletion(): void {
    te('response', 'Kinthic', 'Sub-agents are wired: one cognitive_worker completed in 2 turns.', {
      text: 'Sub-agents are wired: one cognitive_worker completed in 2 turns. Memory admission recorded the session context.',
    }, 300);
    send({ type: 'stream', data: {
      text: 'Sub-agents are wired: one cognitive_worker completed in 2 turns. Memory admission recorded the session context.',
    } }, 320);
    te('memory', 'memory', 'wrote 1 item(s)', { count: 1, items: ['User is testing the production Kinthic TUI locally.'] }, 500);
    te('summary', 'summary', '0.81s · 2 tool(s) · 1 memory', {
      latencyMs: 812,
      tokens: 1240,
      memoriesWritten: 1,
      toolsExecuted: 2,
      workersUsed: 1,
    }, 700);
    setTimeout(() => globalDispatch?.({ type: 'done' }), 1200);
  }
  (globalThis as Record<string, unknown>).__kinthicDemoComplete = fireCompletion;

  send({
    type: 'header',
    data: {
      platform: 'OpenYF (λ) Enterprise', core: 'SILEX Reasoning Engine',
      version: '1.0.0', skillCount: 18, storageMode: 'SQLite + ChromaDB', cwd: '~',
    },
  }, 80);

  send({
    type: 'user_echo',
    data: { text: 'audit the repo and tell me if sub-agents are wired correctly' },
  }, 200);

  te('user', 'You', 'audit the repo and tell me if sub-agents are wired correctly', {
    text: 'audit the repo and tell me if sub-agents are wired correctly',
  }, 220);

  te('routing', 'routing', '[Fast Router] Routed to FAST path', {}, 400);
  te('context', 'context', 'Context assembled from memory and beliefs', {}, 600);
  te('tool', 'tools', '1 tool call(s) planned', {}, 800);

  send({
    type: 'cost_update',
    data: { total_cost_usd: 0.02, total_tokens: 1240, turns: 1, model: 'claude-opus-4.7' },
  }, 900);

  te('subagent', 'cognitive_worker', 'Inspect repository structure and return file summary', {
    worker_id: 'cw-demo-001',
    lifecycle: 'running',
    objective: 'Inspect repository structure and return file summary',
    worker_class: 'cognitive_worker',
    turns_used: 1,
    tokens_used: 920,
    event_id: 'worker-demo-1',
    timestamp: Date.now() / 1000,
  }, 1100);

  send({
    type: 'tool_auth',
    data: {
      toolName: 'code_editor.propose_edit', targetPath: './silex/tools/system.py',
      operationType: '1 local file alteration', txId: 'e8f2b1',
      diffLines: [
        { type: 'context', content: '# process isolation module' },
        { type: 'add',     content: 'import resource' },
        { type: 'remove',  content: 'process = await asyncio.create_subprocess_shell(command)' },
      ],
    },
  }, 2400);

  te('subagent', 'cognitive_worker', 'Inspect repository structure and return file summary', {
    worker_id: 'cw-demo-001',
    lifecycle: 'done',
    objective: 'Inspect repository structure and return file summary',
    worker_class: 'cognitive_worker',
    detail: 'Returned README, pyproject.toml, and scripts/run.py summary.',
    turns_used: 2,
    tokens_used: 1312,
    event_id: 'worker-demo-2',
    timestamp: Date.now() / 1000,
  }, 3200);
}

waitUntilExit()
  .then(() => {
    stopEventReceiver();
    process.exit(0);
  })
  .catch(() => {
    stopEventReceiver();
    process.exit(1);
  });
