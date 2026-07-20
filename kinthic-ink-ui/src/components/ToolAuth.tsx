// ─────────────────────────────────────────────────────────────────────────────
// src/components/ToolAuth.tsx
// Interactive tool authorization interceptor.
//
// Renders when the model requests permission to execute a local tool.
// Uses Ink's useInput() hook to capture 'y' / 'n' / 'Enter' at the line
// cursor. No alternate screen — all inline, history preserved.
//
// State machine:
//   'pending'  → waiting for operator keypress
//   'approved' → renders success banner, fires onApprove callback
//   'rejected' → renders rejection banner, fires onReject callback
// ─────────────────────────────────────────────────────────────────────────────

import React, { useState } from 'react';
import { Box, Text, useInput } from 'ink';
import { colors, symbols } from '../theme.js';
import type { ToolAuthRequest } from '../types.js';

// ── Diff line renderer ─────────────────────────────────────────────────────────
interface DiffLineProps {
  type: 'add' | 'remove' | 'context';
  content: string;
}

const DiffLineRow: React.FC<DiffLineProps> = ({ type, content }) => {
  const prefix = type === 'add' ? '+ ' : type === 'remove' ? '- ' : '  ';
  const color  = type === 'add' ? colors.green : type === 'remove' ? colors.red : colors.dimWhite;
  return (
    <Box paddingLeft={4}>
      <Text color={color}>{prefix}{content}</Text>
    </Box>
  );
};

// ── Prop types ────────────────────────────────────────────────────────────────
interface ToolAuthProps {
  request: ToolAuthRequest;
  isActive: boolean;                   // only capture keys when mounted & active
  onApprove: (txId: string) => void;
  onReject: () => void;
}

type AuthState = 'pending' | 'approved' | 'rejected';

// ── Main component ─────────────────────────────────────────────────────────────
const ToolAuth: React.FC<ToolAuthProps> = ({ request, isActive, onApprove, onReject }) => {
  const [authState, setAuthState] = useState<AuthState>('pending');

  // ── Keyboard capture ──────────────────────────────────────────────────────
  // 'y'     → approve  (explicit confirmation required)
  // 'n' / Escape / Enter → reject  (default N behaviour)
  useInput(
    (input, key) => {
      if (authState !== 'pending') return;

      const ch = input.toLowerCase();

      if (ch === 'y') {
        const txId = request.txId ?? `tx_${Math.random().toString(36).slice(2, 8)}`;
        setAuthState('approved');
        // ── Emit auth_response to Python bridge via stdout ──────────────────
        const packet = JSON.stringify({
          type: 'auth_response',
          approved: true,
          editId: txId,
        });
        process.stderr.write(packet + '\n');
        onApprove(txId);
        return;
      }
      if (ch === 'n' || key.escape || key.return) {
        setAuthState('rejected');
        // ── Emit auth_response to Python bridge via stdout ──────────────────
        const packet = JSON.stringify({
          type: 'auth_response',
          approved: false,
          editId: request.txId ?? '',
        });
        process.stderr.write(packet + '\n');
        onReject();
      }
    },
    { isActive }
  );

  return (
    <Box flexDirection="column" marginTop={1}>

      {/* ── Warning emblem ──────────────────────────────────────────────── */}
      <Box>
        <Text color={colors.amber} bold>
          {symbols.bolt} Tool Authorization Request
        </Text>
      </Box>

      {/* ── Operation breakdown ─────────────────────────────────────────── */}
      <Box flexDirection="column" marginTop={1} paddingLeft={3}>
        <Box>
          <Text color={colors.dimWhite}>{'[TOOL] '}</Text>
          <Text color={colors.white}>{request.toolName}</Text>
          <Text color={colors.dimWhite}>{' ' + symbols.arrow + ' Target: '}</Text>
          <Text color={colors.cyan}>{request.targetPath}</Text>
        </Box>
        <Box marginTop={0}>
          <Text color={colors.dimWhite}>{'       Operation: '}</Text>
          <Text color={colors.white}>{request.operationType}</Text>
        </Box>
      </Box>

      {/* ── Diff summary ────────────────────────────────────────────────── */}
      <Box flexDirection="column" marginTop={1} borderStyle="single" borderColor={colors.separator} paddingX={1}>
        <Box marginBottom={0}>
          <Text color={colors.dimWhite} bold>Diff Summary:</Text>
        </Box>
        {request.diffLines.map((line, i) => (
          <DiffLineRow key={i} type={line.type} content={line.content} />
        ))}
      </Box>

      {/* ── Confirmation prompt ──────────────────────────────────────────── */}
      {authState === 'pending' && (
        <Box marginTop={1} paddingLeft={0}>
          <Text color={colors.prompt} bold>
            {'? '}
          </Text>
          <Text color={colors.white}>
            Approve this system code adjustment?{' '}
          </Text>
          <Text color={colors.dimWhite}>(y/N) </Text>
          <Text color={colors.prompt} bold>{'› '}</Text>
          <Text color={colors.white} inverse> </Text>
        </Box>
      )}

      {/* ── Approved state ───────────────────────────────────────────────── */}
      {authState === 'approved' && (
        <Box flexDirection="column" marginTop={1} paddingLeft={0}>
          <Box>
            <Text color={colors.green} bold>{symbols.check} </Text>
            <Text color={colors.green}>Authorization granted — executing {request.toolName}</Text>
            {request.txId && (
              <Text color={colors.dimWhite}>{' [tx_id: ' + request.txId + ']'}</Text>
            )}
          </Box>
        </Box>
      )}

      {/* ── Rejected state ───────────────────────────────────────────────── */}
      {authState === 'rejected' && (
        <Box marginTop={1}>
          <Text color={colors.red} bold>✘ </Text>
          <Text color={colors.red}>Authorization denied. Operation cancelled.</Text>
        </Box>
      )}

    </Box>
  );
};

export default ToolAuth;
