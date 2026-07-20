// ─────────────────────────────────────────────────────────────────────────────
// src/components/Header.tsx
// Split-block identity dashboard header.
//
// Layout (Yoga flexbox, NO string-replication):
//
//  ┌────────────────────────────────────┬───────────────────────────────────┐
//  │  ASCII KINTHIC art (left, 50%)      │  metadata fields (right, 50%)     │
//  └────────────────────────────────────┴───────────────────────────────────┘
//  ────────────────────────────────── rule ────────────────────────────────────
//
// The outer Box uses borderStyle="single" which renders the top/bottom/side
// borders via Yoga. The vertical separator is a zero-width borderRight on the
// left column. No string replication of '─' or '│' anywhere.
// ─────────────────────────────────────────────────────────────────────────────

import React, { memo } from 'react';
import { Box, Text } from 'ink';
import { colors, symbols } from '../theme.js';
import type { HeaderMetadata } from '../types.js';

// ── ASCII art for "KINTHIC" — 7-line block font ────────────────────────────────
const KINTHIC_ART = [
  ' █  ▀▄▀ █▄▀ █▀▄ █▀█ █▀▀ ',
  ' █▀▀ █  █ █ █▀▄ █ █ ▀▀█ ',
  ' ▀▀▀ ▀  ▀ ▀ ▀ ▀ ▀▀▀ ▀▀▀ ',
];

// Fancier big font block using box-drawing — "KINTHIC" spelled out
const KINTHIC_BIG: string[] = [
  '  ▄█▄ █▀█ █▀█ █▄ █ █▀█ ▄█▀ ',
  '  █▀▄ █▀▄ █ █ █ ▀█ █ █ ▀█▄ ',
  '  ▀ ▀ ▀ ▀ ▀▀▀ ▀  ▀ ▀▀▀ ▀▀▀ ',
];

// Full block-character art, 5 rows (Windows safe, no double box corners)
const ASCII_LINES = [
  '  ██╗  ██╗██╗███╗   ██╗████████╗██╗  ██╗██╗ ██████╗ ',
  '  ██║ ██╔╝██║████╗  ██║╚══██╔══╝██║  ██║██║██╔════╝ ',
  '  █████╔╝ ██║██╔██╗ ██║   ██║   ███████║██║██║      ',
  '  ██╔═██╗ ██║██║╚██╗██║   ██║   ██╔══██║██║██║      ',
  '  ██║  ██╗██║██║ ╚████║   ██║   ██║  ██║██║╚██████╗ ',
  '  ╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝╚═╝ ╚═════╝ ',
];

// ── Sub-components ─────────────────────────────────────────────────────────────

interface MetaRowProps {
  label: string;
  value: string;
}

const MetaRow: React.FC<MetaRowProps> = ({ label, value }) => (
  <Box>
    <Box width={12}>
      <Text color={colors.dimWhite}>{label}</Text>
    </Box>
    <Text color={colors.white}>{value}</Text>
  </Box>
);

// ── Main Header component ──────────────────────────────────────────────────────

interface HeaderProps {
  meta: HeaderMetadata;
}

const Header: React.FC<HeaderProps> = ({ meta }) => {
  const versionStr = `Kinthic Terminal [v${meta.version}]`;

  return (
    <Box flexDirection="column">
      {/* ── Outer panel: no border frame ─── */}
      <Box flexDirection="row">

        {/* ── Left column: KINTHIC ASCII art with only a vertical right border ─── */}
        <Box
          flexDirection="column"
          flexGrow={1}
          flexBasis="50%"
          paddingLeft={1}
          paddingY={1}
          borderStyle="single"
          borderRight
          borderLeft={false}
          borderTop={false}
          borderBottom={false}
          borderColor={colors.separator}
        >
          {ASCII_LINES.map((line, i) => (
            <Text key={i} color={colors.primary}>{line}</Text>
          ))}
        </Box>

        {/* ── Right column: metadata fields ────────────────────────────── */}
        <Box
          flexDirection="column"
          flexGrow={1}
          flexBasis="50%"
          paddingLeft={2}
          paddingY={1}
          justifyContent="center"
        >
          <MetaRow label="Platform: " value={meta.platform} />
          <MetaRow label="Core:     " value={meta.core} />
          <MetaRow label="Interface:" value={versionStr} />
          <MetaRow label="Skills:   " value={`${meta.skillCount} Active Markdown Engines`} />
          <MetaRow label="Storage:  " value={meta.storageMode} />
        </Box>

      </Box>

      {/* ── Horizontal tracking rule (pure Ink border, no string repeat) ─ */}
      <Box borderStyle="single" borderTop borderColor={colors.separator} borderBottom={false} borderLeft={false} borderRight={false}>
        <Text> </Text>
      </Box>
    </Box>
  );
};

// Wrapped in memo: Header content is static after the initial 'header' event.
// This prevents 20×/sec re-renders of 28 Yoga nodes during spinner ticks.
export default memo(Header);
