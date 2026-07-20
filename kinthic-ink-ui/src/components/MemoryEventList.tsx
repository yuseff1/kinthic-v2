import React, { memo } from 'react';
import { Box, Text } from 'ink';
import { colors } from '../theme.js';
import type { MemoryWriteEvent } from '../types.js';

interface MemoryEventListProps {
  events: MemoryWriteEvent[];
}

const MemoryEventList = memo(({ events }: MemoryEventListProps) => {
  const latest = events[events.length - 1];
  if (!latest || latest.count === 0) {
    return (
      <Box flexDirection="column" marginTop={1}>
        <Text color={colors.dimWhite} bold>Memory</Text>
        <Text color={colors.dimWhite}>No memory writes this turn</Text>
      </Box>
    );
  }

  return (
    <Box flexDirection="column" marginTop={1}>
      <Text color={colors.green} bold>Memory Writes +{latest.count}</Text>
      {(latest.items ?? []).slice(0, 3).map((item, idx) => (
        <Text key={`${idx}-${item}`} color={colors.dimWhite}>• {item}</Text>
      ))}
    </Box>
  );
});

export default MemoryEventList;
