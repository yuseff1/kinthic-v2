// Single-column chronological activity ledger.

import React, { memo } from 'react';
import { Box, useStdout } from 'ink';
import type { ApprovalRequest, ToolAuthRequest } from '../types.js';
import type { LedgerItem, ThinkingPhase } from '../state.js';
import { prepareDisplayLedger } from '../state.js';
import { FileEditApprovalPrompt } from './FileEditApprovalPrompt.js';
import { ApprovalPrompt } from './ApprovalPrompt.js';
import ThinkingSpinner from './ThinkingSpinner.js';
import {
  ApprovalResultLedgerRow,
  AssistantLedgerRow,
  ErrorLedgerRow,
  IdleLedgerHint,
  MemoryLedgerRow,
  StreamingLedgerRow,
  ThinkingLedgerRow,
  TurnSummaryLedgerRow,
  UserLedgerRow,
  WorkerLedgerRow,
} from './LedgerRow.js';

interface ActivityLedgerProps {
  ledger: LedgerItem[];
  streamingText?: string | null;
  thinking: ThinkingPhase;
  toolAuth: ToolAuthRequest | null;
  approvalQueue: ApprovalRequest[];
  authMode: boolean;
  onToolApprove: (txId: string) => void;
  onToolReject: () => void;
  onApprovalApprove: (id: string) => void;
  onApprovalReject: (id: string) => void;
}

function renderLedgerItem(item: LedgerItem): React.ReactNode {
  switch (item.kind) {
    case 'user':
      return <UserLedgerRow key={item.id} text={item.text} />;
    case 'assistant':
      return <AssistantLedgerRow key={item.id} text={item.text} />;
    case 'thinking':
      return (
        <ThinkingLedgerRow
          key={item.id}
          status={item.status}
          detail={item.detail}
          turnPhase={item.turnPhase}
        />
      );
    case 'worker':
      return <WorkerLedgerRow key={item.id} data={item.data} />;
    case 'memory':
      return <MemoryLedgerRow key={item.id} data={item.data} />;
    case 'tool_auth':
      return null;
    case 'approval':
      return null;
    case 'approval_result':
      return (
        <ApprovalResultLedgerRow
          key={item.id}
          data={item.data}
          approved={item.approved}
        />
      );
    case 'error':
      return <ErrorLedgerRow key={item.id} message={item.message} />;
    case 'telemetry':
      return (
        <TurnSummaryLedgerRow
          key={item.id}
          telemetry={item.data}
          workersUsed={item.workersUsed}
        />
      );
    default:
      return null;
  }
}

const ActivityLedger = memo(({
  ledger,
  streamingText,
  thinking,
  toolAuth,
  approvalQueue,
  authMode,
  onToolApprove,
  onToolReject,
  onApprovalApprove,
  onApprovalReject,
}: ActivityLedgerProps) => {
  const { stdout } = useStdout();
  const rows = stdout?.rows ?? 32;
  const minHeight = Math.max(6, rows - 14);
  const displayLedger = prepareDisplayLedger(ledger, streamingText);
  const empty = displayLedger.length === 0 && !streamingText && thinking.phase !== 'thinking';
  const showSpinner = thinking.phase === 'thinking' && !streamingText;

  return (
    <Box flexDirection="column" minHeight={minHeight} flexGrow={1} marginTop={1}>
      {empty ? <IdleLedgerHint /> : displayLedger.map(renderLedgerItem)}

      {showSpinner ? <ThinkingSpinner state={thinking} /> : null}

      {streamingText && streamingText.length > 0 ? (
        <StreamingLedgerRow text={streamingText} />
      ) : null}

      {toolAuth && authMode ? (
        <FileEditApprovalPrompt
          request={toolAuth}
          isActive={authMode}
          onApprove={onToolApprove}
          onReject={onToolReject}
        />
      ) : null}

      {approvalQueue.length > 0 ? (
        <ApprovalPrompt
          queue={approvalQueue}
          onApprove={onApprovalApprove}
          onReject={onApprovalReject}
        />
      ) : null}
    </Box>
  );
});

export default ActivityLedger;
