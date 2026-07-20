// ─────────────────────────────────────────────────────────────────────────────
// src/components/ThinkingSpinner.tsx  (v2 — event-driven sub-steps)
//
// State machine:
//   idle     → hidden (renders null)
//   thinking → spinner + live sub-step lines driven by incoming detail strings
//   done     → collapses to null instantly (no trail left behind)
//
// Sub-step behaviour:
//   • Each new { detail } string from an incoming 'thinking' packet is appended
//     as a new sub-step line using its label + detail text.
//   • Steps are capped at MAX_STEPS to prevent unbounded growth.
//   • On transition to 'done' the list is cleared, leaving zero residual lines.
//
// In-place rendering:
//   Ink's reconciler updates only the changed virtual DOM nodes, so steps appear
//   to morph in-place without cursor drift or line duplication.
// ─────────────────────────────────────────────────────────────────────────────

import React, { memo, useEffect, useRef, useState } from 'react';
import { Box, Text } from 'ink';
import Spinner from 'ink-spinner';
import { colors } from '../theme.js';
import type { ThinkingPhase } from '../state.js';

export type { ThinkingPhase };

interface Step {
  label:  string;
  detail: string;
}

interface ThinkingSpinnerProps {
  state: ThinkingPhase;
}

const MAX_STEPS = 6;

// ── Derive a short display label from the detail string ──────────────────────
function extractLabel(detail: string): string {
  // e.g. "[Fast Router] Routed to FAST path" → "Fast Router"
  const m = detail.match(/^\[([^\]]+)\]/);
  if (m) return m[1];
  // e.g. "3 tool call(s) planned" → "Tools"
  if (/tool/i.test(detail)) return 'Tools';
  if (/critic/i.test(detail))  return 'Critic';
  if (/context/i.test(detail)) return 'Context';
  if (/memory/i.test(detail))  return 'Memory';
  if (/router/i.test(detail))  return 'Router';
  return 'Step';
}

// ── Main component ────────────────────────────────────────────────────────────
const ThinkingSpinner: React.FC<ThinkingSpinnerProps> = memo(({ state }) => {
  const [steps, setSteps] = useState<Step[]>([]);
  // Track the last detail string we processed so duplicate events are ignored
  const lastDetail = useRef<string | null>(null);

  useEffect(() => {
    if (state.phase === 'idle' || state.phase === 'done') {
      // Collapse — clear all steps immediately
      setSteps([]);
      lastDetail.current = null;
      return;
    }

    if (state.phase === 'thinking' && state.detail) {
      const detail = state.detail.trim();
      if (detail && detail !== lastDetail.current) {
        lastDetail.current = detail;
        setSteps(prev => {
          // Strip [Bracket] prefix from the stored detail for display
          const cleanDetail = detail.replace(/^\[[^\]]+\]\s*/, '');
          const label = extractLabel(detail);
          const next = [...prev, { label, detail: cleanDetail }];
          // Keep only the most recent MAX_STEPS
          return next.length > MAX_STEPS ? next.slice(-MAX_STEPS) : next;
        });
      }
    }
  }, [state]);

  if (state.phase === 'idle' || state.phase === 'done') {
    return null;
  }

  return (
    <Box flexDirection="column" marginTop={1}>

      {/* ── Primary spinner line ─────────────────────────────────────── */}
      <Box>
        <Text color={colors.cyan}>
          <Spinner type="dots" />
        </Text>
        <Text color={colors.white}>{' '}{state.status ?? 'Thinking...'}</Text>
      </Box>

      {/* ── Live sub-step lines — update in-place via Ink reconciler ── */}
      {steps.map((step, i) => (
        <Box key={i} paddingLeft={2}>
          <Text color={colors.dimWhite}>{'↳ '}</Text>
          <Text color={colors.dimWhite} bold>{'[' + step.label + '] '}</Text>
          <Text color={colors.dimWhite}>{step.detail}</Text>
        </Box>
      ))}

    </Box>
  );
});

export default ThinkingSpinner;
