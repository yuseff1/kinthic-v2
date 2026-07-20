// File-edit approval prompt — same Allow/Deny pattern as tool approvals.

import React, { useState } from 'react';
import { Box, Text, useInput } from 'ink';
import { colors } from '../theme.js';
import type { ToolAuthRequest } from '../types.js';

interface FileEditApprovalPromptProps {
  request: ToolAuthRequest;
  isActive: boolean;
  onApprove: (txId: string) => void;
  onReject: () => void;
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

export const FileEditApprovalPrompt: React.FC<FileEditApprovalPromptProps> = ({
  request,
  isActive,
  onApprove,
  onReject,
}) => {
  const [choice, setChoice] = useState(0);

  useInput((input, key) => {
    if (!isActive) return;

    const ch = input.toLowerCase();
    if (ch === 'y') {
      const txId = request.txId ?? `tx_${Math.random().toString(36).slice(2, 8)}`;
      process.stderr.write(JSON.stringify({
        type: 'auth_response',
        approved: true,
        editId: txId,
      }) + '\n');
      onApprove(txId);
      setChoice(0);
      return;
    }
    if (ch === 'n') {
      process.stderr.write(JSON.stringify({
        type: 'auth_response',
        approved: false,
        editId: request.txId ?? '',
      }) + '\n');
      onReject();
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
      if (choice === 0) {
        const txId = request.txId ?? `tx_${Math.random().toString(36).slice(2, 8)}`;
        process.stderr.write(JSON.stringify({
          type: 'auth_response',
          approved: true,
          editId: txId,
        }) + '\n');
        onApprove(txId);
      } else {
        process.stderr.write(JSON.stringify({
          type: 'auth_response',
          approved: false,
          editId: request.txId ?? '',
        }) + '\n');
        onReject();
      }
      setChoice(0);
    }
  }, { isActive });

  if (!isActive) return null;

  return (
    <Box flexDirection="column" marginTop={1} paddingLeft={2}>
      <Text color={colors.amber} bold>File edit approval</Text>
      <Box marginTop={1}>
        <Text color={colors.cyan} bold>{request.toolName}</Text>
        <Text color={colors.dimWhite}>  ·  {request.operationType}</Text>
      </Box>
      <Box marginTop={1} paddingLeft={2}>
        <Text color={colors.dimWhite}>{request.targetPath}</Text>
      </Box>
      {(request.diffLines ?? []).slice(0, 30).map((line, idx) => (
        <Box key={`${idx}-${line.content}`} paddingLeft={2}>
          <Text
            color={
              line.type === 'add' ? colors.green
                : line.type === 'remove' ? colors.red
                  : colors.dimWhite
            }
          >
            {line.type === 'add' ? '+ ' : line.type === 'remove' ? '- ' : '  '}
            {line.content.slice(0, 100)}
          </Text>
        </Box>
      ))}
      {(request.diffLines ?? []).length > 30 && (
        <Box paddingLeft={2}>
          <Text color={colors.dimWhite} dimColor>
            ... and {(request.diffLines ?? []).length - 30} more lines
          </Text>
        </Box>
      )}
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
