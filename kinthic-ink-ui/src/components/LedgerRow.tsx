// Compact ledger row primitives — Claude Code-style activity lines.

import React, { memo } from 'react';
import { Box, Text } from 'ink';
import { colors } from '../theme.js';
import type {
  ApprovalRequest,
  MemoryWriteEvent,
  TelemetryData,
  ToolAuthRequest,
  WorkerEventData,
} from '../types.js';
import MarkdownText from './MarkdownText.js';

export function thinkingKind(status: string, detail?: string): string {
  const blob = `${status} ${detail ?? ''}`.toLowerCase();
  if (blob.includes('router') || blob.includes('routed')) return 'routing';
  if (blob.includes('context') || blob.includes('paging')) return 'context';
  if (blob.includes('tool') || blob.includes('execut')) return 'tool';
  if (blob.includes('memor')) return 'memory';
  if (blob.includes('generat') || blob.includes('response')) return 'response';
  return 'thinking';
}

const Detail = ({ children }: { children: React.ReactNode }) => (
  <Box paddingLeft={2}>
    <Text color={colors.dimWhite}>{children}</Text>
  </Box>
);

export const UserLedgerRow = memo(({ text }: { text: string }) => (
  <Box flexDirection="column" marginTop={1}>
    <Text color={colors.gold} bold>You</Text>
    <Text color={colors.white}>{text}</Text>
  </Box>
));

export const AssistantLedgerRow = memo(({ text }: { text: string }) => (
  <Box flexDirection="column" marginTop={1}>
    <Text color={colors.cyan} bold>Kinthic</Text>
    <MarkdownText text={text} />
  </Box>
));

export const StreamingLedgerRow = memo(({ text }: { text: string }) => (
  <Box flexDirection="column" marginTop={1}>
    <Text color={colors.cyan} bold>Kinthic</Text>
    <MarkdownText text={text} />
    <Text color={colors.dimWhite}>▌</Text>
  </Box>
));

export const ThinkingLedgerRow = memo(({
  status,
  detail,
  turnPhase,
}: {
  status: string;
  detail?: string;
  turnPhase?: string;
}) => {
  const kind = turnPhase ?? thinkingKind(status, detail);
  return (
    <Box flexDirection="column" marginTop={1}>
      <Box>
        <Text color={colors.amber}>● </Text>
        <Text color={colors.white}>{kind}</Text>
        {status && !turnPhase && kind === 'thinking' ? (
          <Text color={colors.dimWhite}>  {status}</Text>
        ) : null}
      </Box>
      {detail ? <Detail>{detail}</Detail> : null}
    </Box>
  );
});

const workerColor = (lifecycle: string): string => {
  switch (lifecycle) {
    case 'running': return colors.cyan;
    case 'done': return colors.green;
    case 'failed': return colors.red;
    case 'killed': return colors.amber;
    default: return colors.dimWhite;
  }
};

export const WorkerLedgerRow = memo(({ data }: { data: WorkerEventData }) => {
  const ancestry = data.ancestry_chain?.length ? ` depth ${data.ancestry_chain.length}` : '';
  const budget = [
    data.turns_used !== undefined ? `${data.turns_used} turns` : '',
    data.tokens_used !== undefined ? `${data.tokens_used.toLocaleString()} tok` : '',
  ].filter(Boolean).join(' · ');

  return (
    <Box flexDirection="column" marginTop={1}>
      <Box>
        <Text color={workerColor(data.lifecycle)}>● </Text>
        <Text color={colors.white}>sub-agent  </Text>
        <Text color={colors.cyan}>{data.worker_class ?? 'worker'}</Text>
        <Text color={colors.dimWhite}>  {data.worker_id.slice(0, 10)}  </Text>
        <Text color={workerColor(data.lifecycle)}>{data.lifecycle}</Text>
        <Text color={colors.dimWhite}>{ancestry}</Text>
      </Box>
      {data.objective ? <Detail>{data.objective.slice(0, 90)}</Detail> : null}
      {budget ? <Detail>{budget}</Detail> : null}
      {data.detail ? <Detail>{data.detail.slice(0, 90)}</Detail> : null}
    </Box>
  );
});

export const MemoryLedgerRow = memo(({ data }: { data: MemoryWriteEvent }) => (
  <Box flexDirection="column" marginTop={1}>
    <Box>
      <Text color={colors.green}>● </Text>
      <Text color={colors.white}>memory  </Text>
      <Text color={colors.dimWhite}>wrote {data.count} item{data.count === 1 ? '' : 's'}</Text>
    </Box>
    {(data.items ?? []).slice(0, 2).map((item, idx) => (
      <Detail key={`${idx}-${item}`}>{item.slice(0, 88)}</Detail>
    ))}
  </Box>
));

export const ToolAuthLedgerRow = memo(({ data }: { data: ToolAuthRequest }) => (
  <Box flexDirection="column" marginTop={1}>
    <Box>
      <Text color={colors.amber}>● </Text>
      <Text color={colors.white}>approval required  </Text>
      <Text color={colors.cyan}>{data.toolName}</Text>
    </Box>
    <Detail>{data.targetPath} · {data.operationType}</Detail>
    <Detail>[y] approve  [n] reject</Detail>
  </Box>
));

export const ApprovalResultLedgerRow = memo(({
  data,
  approved,
}: {
  data: ApprovalRequest;
  approved: boolean;
}) => (
  <Box marginTop={1}>
    <Text color={approved ? colors.green : colors.red}>● </Text>
    <Text color={colors.dimWhite}>{approved ? 'allowed' : 'denied'}  </Text>
    <Text color={colors.cyan}>{data.tool_name}</Text>
    <Text color={colors.dimWhite}>  ·  {data.risk_level.replace(/_/g, ' ')}</Text>
  </Box>
));

export const ErrorLedgerRow = memo(({ message }: { message: string }) => (
  <Box flexDirection="column" marginTop={1}>
    <Box>
      <Text color={colors.red}>● </Text>
      <Text color={colors.red} bold>error</Text>
    </Box>
    <Detail>{message}</Detail>
  </Box>
));

export const TurnSummaryLedgerRow = memo(({
  telemetry,
  workersUsed,
}: {
  telemetry: TelemetryData;
  workersUsed: number;
}) => (
  <Box marginTop={1}>
    <Text color={colors.dimWhite}>
      {'── '}
      {(telemetry.latencyMs / 1000).toFixed(2)}s · {telemetry.toolsExecuted} tool(s) ·{' '}
      {telemetry.memoriesWritten} memory · {telemetry.tokens.toLocaleString()} tok
      {workersUsed > 0 ? ` · ${workersUsed} sub-agent${workersUsed === 1 ? '' : 's'}` : ' · single-agent turn'}
      {' '}
      {'─'.repeat(8)}
    </Text>
  </Box>
));

export const IdleLedgerHint = memo(() => (
  <Box flexDirection="column" marginTop={1}>
    <Text color={colors.white}>Kinthic is ready.</Text>
    <Text color={colors.dimWhite}>Type a message or / for commands.</Text>
  </Box>
));
