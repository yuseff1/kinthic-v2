// ─────────────────────────────────────────────────────────────────────────────
// src/components/TelemetryBar.tsx
// Streamlined post-execution performance metrics footer.
// ─────────────────────────────────────────────────────────────────────────────

import React from 'react';
import { Box, Text } from 'ink';
import { colors, symbols } from '../theme.js';
import type { TelemetryData } from '../types.js';

interface TelemetryBarProps {
  data: TelemetryData;
}

const Pipe: React.FC = () => (
  <Text color={colors.separator}>{`  ${symbols.vbar}  `}</Text>
);

const TelemetryBar: React.FC<TelemetryBarProps> = ({ data }) => {
  const latencyStr = `${(data.latencyMs / 1000).toFixed(2)}s Latency`;
  
  const formatTokens = (t: number): string => {
    if (t >= 1000) {
      const val = (t / 1000).toFixed(1).replace(/\.0$/, '');
      return `${val}k tokens`;
    }
    return `${t} ${t === 1 ? 'token' : 'tokens'}`;
  };
  const tokensStr = formatTokens(data.tokens);
  
  const memStr = `+${data.memoriesWritten} ${data.memoriesWritten === 1 ? 'memory' : 'memories'}`;
  
  const toolsStr = `${data.toolsExecuted} ${data.toolsExecuted === 1 ? 'tool' : 'tools'} executed`;

  return (
    <Box marginTop={1} flexDirection="row">
      <Text color={colors.dimWhite} dimColor>{'[ '}</Text>
      <Text color={colors.dimWhite} dimColor>{latencyStr}</Text>
      <Pipe />
      <Text color={colors.dimWhite} dimColor>{tokensStr}</Text>
      <Pipe />
      <Text color={colors.dimWhite} dimColor>{memStr}</Text>
      <Pipe />
      <Text color={colors.dimWhite} dimColor>{toolsStr}</Text>
      <Text color={colors.dimWhite} dimColor>{' ]'}</Text>
    </Box>
  );
};

export default TelemetryBar;
