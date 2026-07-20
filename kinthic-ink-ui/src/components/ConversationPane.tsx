// ─────────────────────────────────────────────────────────────────────────────
// src/components/ConversationPane.tsx
// Memoized scrollback — isolated from prompt keystroke updates.
// Assistant messages are rendered through MarkdownText for rich formatting.
// ─────────────────────────────────────────────────────────────────────────────

import React, { memo } from 'react';
import { Box, Text } from 'ink';
import { colors } from '../theme.js';
import type { HistoryEntry } from '../state.js';
import MarkdownText from './MarkdownText.js';

interface HistoryEntryRowProps {
  role: 'user' | 'assistant';
  text: string;
}

const HistoryEntryRow = memo(({ role, text }: HistoryEntryRowProps) => (
  <Box flexDirection="column" marginTop={1}>
    {role === 'user' ? (
      <Box borderStyle="round" borderColor={colors.gold} paddingX={1}>
        <Text color={colors.gold} bold>{'You '}</Text>
        <Text color="#F8F8F2">{text}</Text>
      </Box>
    ) : (
      <Box flexDirection="column" borderStyle="round" borderColor={colors.separator} paddingX={1}>
        <Text color={colors.cyan} bold>Kinthic</Text>
        <MarkdownText text={text} />
      </Box>
    )}
  </Box>
));

interface ConversationPaneProps {
  history: HistoryEntry[];
  /** Text currently being streamed (typewriter animation). Null when idle. */
  streamingText?: string | null;
}

const ConversationPane = memo(({ history, streamingText }: ConversationPaneProps) => (
  <>
    {history.map(entry => (
      <HistoryEntryRow key={entry.id} role={entry.role} text={entry.text} />
    ))}
    {streamingText && streamingText.length > 0 && (
      <Box flexDirection="column" marginTop={1} borderStyle="round" borderColor={colors.cyan} paddingX={1}>
        <Text color={colors.cyan} bold>Kinthic</Text>
        <MarkdownText text={streamingText} />
        <Text color="#6272A4" dimColor>▌</Text>
      </Box>
    )}
  </>
));

export default ConversationPane;
