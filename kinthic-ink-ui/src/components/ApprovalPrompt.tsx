// Interactive tool-approval prompt — Allow/Deny with Enter confirmation.

import React, { useState } from 'react';
import { Box, Text, useInput } from 'ink';
import { colors } from '../theme.js';
import type { ApprovalRequest } from '../types.js';

interface ApprovalPromptProps {
  queue: ApprovalRequest[];
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
}

function formatRisk(risk: string): string {
  return risk.replace(/_/g, ' ');
}

function formatSummary(req: ApprovalRequest): string {
  const raw = req.reason.trim();
  const prefix = `Error: Approval required for ${req.tool_name}`;
  if (raw.startsWith(prefix)) {
    return `Kinthic wants to run this tool (${formatRisk(req.risk_level)} access).`;
  }
  if (raw.startsWith('Error:')) {
    return raw.replace(/^Error:\s*/, '').slice(0, 100);
  }
  return raw.slice(0, 100);
}

interface ChoiceRowProps {
  label: string;
  selected: boolean;
  color: string;
}

const ChoiceRow: React.FC<ChoiceRowProps> = ({ label, selected, color }) => (
  <Box>
    <Box width={2}>
      <Text color={selected ? colors.gold : colors.dimWhite}>{selected ? '›' : ' '}</Text>
    </Box>
    <Text color={selected ? color : colors.dimWhite} bold={selected}>
      {label}
    </Text>
  </Box>
);

export const ApprovalPrompt: React.FC<ApprovalPromptProps> = ({
  queue,
  onApprove,
  onReject,
}) => {
  const [requestIdx, setRequestIdx] = useState(0);
  const [choice, setChoice] = useState(0); // 0 = allow, 1 = deny

  const safeRequestIdx = Math.min(requestIdx, Math.max(0, queue.length - 1));
  const current = queue[safeRequestIdx];

  useInput((input, key) => {
    if (!current) return;

    const ch = input.toLowerCase();

    if (ch === 'y') {
      onApprove(current.approval_id);
      setChoice(0);
      return;
    }
    if (ch === 'n') {
      onReject(current.approval_id);
      setChoice(0);
      return;
    }
    if (key.upArrow || key.leftArrow) {
      setChoice(0);
      return;
    }
    if (key.downArrow || key.rightArrow) {
      setChoice(1);
      return;
    }
    if (key.return) {
      if (choice === 0) onApprove(current.approval_id);
      else onReject(current.approval_id);
      setChoice(0);
      return;
    }
    if (key.tab && queue.length > 1) {
      setRequestIdx(prev => (prev + 1) % queue.length);
      setChoice(0);
    }
  });

  if (!current) return null;

  return (
    <Box flexDirection="column" marginTop={1} paddingLeft={2}>
      <Text color={colors.amber} bold>
        Tool approval{queue.length > 1 ? ` (${safeRequestIdx + 1}/${queue.length})` : ''}
      </Text>
      <Box marginTop={1}>
        <Text color={colors.cyan} bold>{current.tool_name}</Text>
        <Text color={colors.dimWhite}>  ·  {formatRisk(current.risk_level)}</Text>
      </Box>
      <Box marginTop={1} paddingLeft={2}>
        <Text color={colors.dimWhite}>{formatSummary(current)}</Text>
      </Box>
      <Box flexDirection="column" marginTop={1}>
        <ChoiceRow label="Allow once" selected={choice === 0} color={colors.green} />
        <ChoiceRow label="Deny" selected={choice === 1} color={colors.red} />
      </Box>
      <Box marginTop={1} paddingLeft={2}>
        <Text color={colors.dimWhite}>↑↓ select · Enter confirm · y/n</Text>
      </Box>
    </Box>
  );
};
