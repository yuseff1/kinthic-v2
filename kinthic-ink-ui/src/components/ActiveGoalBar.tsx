// ActiveGoalBar.tsx — Shows the currently executing background goal
import React from 'react';
import { Box, Text } from 'ink';
import type { ActiveGoal, CostSummary } from '../types.js';

const STATUS_COLORS: Record<string, string> = {
  running: 'green',
  pending: 'yellow',
  completed: 'cyan',
  failed: 'red',
};

interface Props {
  goal: ActiveGoal | null;
  cost: CostSummary;
}

export const ActiveGoalBar: React.FC<Props> = ({ goal, cost }) => {
  const hasActivity = goal !== null || cost.total_tokens > 0;
  if (!hasActivity) return null;

  return (
    <Box flexDirection="row" gap={2} paddingX={1} marginBottom={1}>
      {goal && (
        <Box flexDirection="row" gap={1}>
          <Text color={STATUS_COLORS[goal.status] ?? 'white'} bold>
            ◉
          </Text>
          <Text bold>Goal:</Text>
          <Text color="cyan">{goal.description.slice(0, 60)}</Text>
          <Text color={STATUS_COLORS[goal.status] ?? 'white'} dimColor>
            [{goal.status}]
          </Text>
        </Box>
      )}
      {cost.total_tokens > 0 && (
        <Box flexDirection="row" gap={1}>
          <Text color="gray" dimColor>│</Text>
          <Text color="gray">
            {cost.total_tokens.toLocaleString()} tok
            {cost.total_cost_usd > 0 ? ` · $${cost.total_cost_usd.toFixed(4)}` : ''}
            {` · T${cost.turns}`}
          </Text>
        </Box>
      )}
    </Box>
  );
};
