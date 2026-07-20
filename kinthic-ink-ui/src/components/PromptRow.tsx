// ─────────────────────────────────────────────────────────────────────────────
// src/components/PromptRow.tsx
// Anchored prompt footer with thin separator hints.
// ─────────────────────────────────────────────────────────────────────────────

import React, { memo } from 'react';
import { Box, Text } from 'ink';
import TextInput from './TextInput.js';
import { colors } from '../theme.js';

interface PromptRowProps {
  isActive: boolean;
  turnCounter: number;
  commands: Array<{ cmd: string; args: string; desc: string }>;
  cwd?: string;
  history?: string[];
  modelHint?: string;
  showEscHint?: boolean;
  onSubmit: (text: string) => void;
}

function abbreviateCwd(cwd: string): string {
  if (!cwd || cwd === '~') return '~';
  const normalized = cwd.replace(/\\/g, '/');
  const home = process.env['HOME'] || process.env['USERPROFILE'] || '';
  const withTilde = home ? normalized.replace(home.replace(/\\/g, '/'), '~') : normalized;
  const parts = withTilde.split('/').filter(Boolean);
  if (parts.length <= 2) return withTilde;
  return '~/' + parts.slice(-2).join('/');
}

const PromptRow = memo(({
  isActive,
  turnCounter,
  commands,
  cwd = '~',
  history = [],
  modelHint = 'router:auto',
  showEscHint = false,
  onSubmit,
}: PromptRowProps) => (
  <Box marginTop={1} flexDirection="column">
    <Box>
      <Text color={colors.gold} bold>{'λ '}</Text>
      <Text color={colors.gold} dimColor>{abbreviateCwd(cwd)} {'› '}</Text>
      <TextInput
        isActive={isActive}
        resetToken={turnCounter}
        onSubmit={onSubmit}
        placeholder={isActive ? 'Type a message or /command…' : ''}
        commands={commands}
        history={history}
      />
    </Box>
    <Box paddingLeft={2} marginTop={1}>
      <Text color={colors.dimWhite}>
        {modelHint}
        {' · '}
        {abbreviateCwd(cwd)}
        {showEscHint ? ' · Esc cancel' : ''}
      </Text>
    </Box>
  </Box>
));

export default PromptRow;
