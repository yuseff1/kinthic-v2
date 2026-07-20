// ─────────────────────────────────────────────────────────────────────────────
// src/App.tsx  (v6 — ledger shell: single-column activity stream)
// ─────────────────────────────────────────────────────────────────────────────

import React, { useState, useCallback, useEffect, useRef } from 'react';
import { Box, useApp, useInput } from 'ink';

import Header from './components/Header.js';
import ActivityLedger from './components/ActivityLedger.js';
import PromptRow from './components/PromptRow.js';
import { colors } from './theme.js';

import type { IncomingMessage } from './types.js';
import {
  INITIAL_STATE,
  reduceAppState,
  reduceUserSubmit,
  reduceAuthDecision,
  type AppState,
} from './state.js';

interface AppProps {
  registerDispatch: (fn: (msg: IncomingMessage) => void) => void;
}

const App: React.FC<AppProps> = ({ registerDispatch }) => {
  const { exit } = useApp();
  const [state, setState] = useState<AppState>(INITIAL_STATE);

  const streamBufferRef = useRef<string>('');
  const streamWordIdxRef = useRef<number>(0);
  const [streamDisplayText, setStreamDisplayText] = useState<string>('');

  useEffect(() => {
    if (state.streamingText === null) {
      streamBufferRef.current = '';
      streamWordIdxRef.current = 0;
      setStreamDisplayText('');
      return;
    }

    const text = state.streamingText;
    streamBufferRef.current = text;
    streamWordIdxRef.current = 0;

    // Short replies: show immediately (no artificial typewriter delay)
    if (text.length <= 200) {
      setStreamDisplayText(text);
      setState(prev => reduceAppState(prev, {
        type: 'response',
        data: { text },
      }));
      setStreamDisplayText('');
      return;
    }

    const words = text.split(/(\s+)/);

    const interval = setInterval(() => {
      const idx = streamWordIdxRef.current;
      if (idx >= words.length) {
        clearInterval(interval);
        setState(prev => reduceAppState(prev, {
          type: 'response',
          data: { text: streamBufferRef.current },
        }));
        setStreamDisplayText('');
        return;
      }
      const revealed = words.slice(0, idx + 1).join('');
      setStreamDisplayText(revealed);
      streamWordIdxRef.current = idx + 1;
    }, 18);

    return () => clearInterval(interval);
  }, [state.streamingText]);

  const dispatch = useCallback((msg: IncomingMessage) => {
    setState(prev => reduceAppState(prev, msg));
  }, []);

  useEffect(() => { registerDispatch(dispatch); }, [registerDispatch, dispatch]);

  useEffect(() => {
    if (state.mode === 'done') {
      const t = setTimeout(() => exit(), 80);
      return () => clearTimeout(t);
    }
  }, [state.mode, exit]);

  const handleSubmit = useCallback((text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;

    setState(prev => reduceUserSubmit(prev, trimmed));

    const packet = JSON.stringify({
      type: 'user_input',
      params: { text: trimmed },
    });
    process.stderr.write(packet + '\n');
  }, []);

  const handleApprove = useCallback((txId: string) => {
    setState(prev => reduceAuthDecision(prev, true));
    const demoComplete = (globalThis as Record<string, unknown>).__kinthicDemoComplete;
    if (typeof demoComplete === 'function') demoComplete();
    void txId;
  }, []);

  const handleReject = useCallback(() => {
    setState(prev => reduceAuthDecision(prev, false));
    const demoComplete = (globalThis as Record<string, unknown>).__kinthicDemoComplete;
    if (typeof demoComplete === 'function') demoComplete();
  }, []);

  const handleApprovalApprove = useCallback((id: string) => {
    const packet = JSON.stringify({
      type: 'approval_response',
      params: { id, approved: true },
    });
    process.stderr.write(packet + '\n');
    setState(prev => reduceAppState(prev, {
      type: 'approval_resolved',
      data: { approval_id: id, approved: true },
    }));
  }, []);

  const handleApprovalReject = useCallback((id: string) => {
    const packet = JSON.stringify({
      type: 'approval_response',
      params: { id, approved: false },
    });
    process.stderr.write(packet + '\n');
    setState(prev => reduceAppState(prev, {
      type: 'approval_resolved',
      data: { approval_id: id, approved: false },
    }));
  }, []);

  useInput((input, key) => {
    void input;
    if (key.escape && state.mode === 'thinking') {
      process.stderr.write(JSON.stringify({ type: 'cancel_request' }) + '\n');
      setState(prev => ({
        ...prev,
        mode: 'prompt',
        thinking: { phase: 'done' },
        streamingText: null,
      }));
    }
  });

  const inputActive = state.mode === 'prompt';
  const modelHint = state.cost.model || 'router:auto';

  return (
    <Box flexDirection="column">
      <Header meta={state.header} />
      <ActivityLedger
        ledger={state.ledger}
        streamingText={streamDisplayText || null}
        thinking={state.thinking}
        toolAuth={state.toolAuth}
        approvalQueue={state.approvalQueue}
        authMode={state.mode === 'auth'}
        onToolApprove={handleApprove}
        onToolReject={handleReject}
        onApprovalApprove={handleApprovalApprove}
        onApprovalReject={handleApprovalReject}
      />
      <Box
        borderStyle="single"
        borderTop
        borderBottom={false}
        borderLeft={false}
        borderRight={false}
        borderColor={colors.separator}
        marginTop={1}
      >
        <Box height={0} />
      </Box>
      <PromptRow
        isActive={inputActive}
        turnCounter={state.turnCounter}
        commands={state.commands}
        cwd={state.header.cwd}
        history={state.inputHistory}
        modelHint={modelHint}
        showEscHint={state.mode === 'thinking'}
        onSubmit={handleSubmit}
      />
    </Box>
  );
};

export default App;
