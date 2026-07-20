// ─────────────────────────────────────────────────────────────────────────────
// src/components/MarkdownText.tsx
// Lightweight Markdown → Ink renderer for the 6 most common patterns.
//
// Handled:
//   ``` code blocks      → bordered box in green
//   **bold**             → bold text
//   `inline code`        → cyan text
//   - / * / 1. lists     → bullet or numbered items
//   # / ## / ### headers → bold + underline, with optional colour
//   plain text           → white, word-wrapped
// ─────────────────────────────────────────────────────────────────────────────

import React from 'react';
import { Box, Text } from 'ink';

interface MarkdownTextProps {
  text: string;
}

// ── Inline span renderer ──────────────────────────────────────────────────────

function renderInline(line: string, key: string | number): React.ReactNode {
  // Split on **bold** and `code` tokens
  const parts: React.ReactNode[] = [];
  let remaining = line;
  let i = 0;

  while (remaining.length > 0) {
    // Bold: **text**
    const boldMatch = remaining.match(/^(.*?)\*\*(.+?)\*\*(.*)/s);
    // Inline code: `text`
    const codeMatch = remaining.match(/^(.*?)`([^`]+)`(.*)/s);

    if (!boldMatch && !codeMatch) {
      parts.push(<Text key={`${key}-t${i}`} color="#F8F8F2">{remaining}</Text>);
      break;
    }

    // Pick whichever match starts earlier
    const boldStart = boldMatch ? boldMatch[1].length : Infinity;
    const codeStart = codeMatch ? codeMatch[1].length : Infinity;

    if (boldStart <= codeStart && boldMatch) {
      if (boldMatch[1]) {
        parts.push(<Text key={`${key}-t${i}`} color="#F8F8F2">{boldMatch[1]}</Text>);
        i++;
      }
      parts.push(<Text key={`${key}-b${i}`} color="#F8F8F2" bold>{boldMatch[2]}</Text>);
      i++;
      remaining = boldMatch[3];
    } else if (codeMatch) {
      if (codeMatch[1]) {
        parts.push(<Text key={`${key}-t${i}`} color="#F8F8F2">{codeMatch[1]}</Text>);
        i++;
      }
      parts.push(
        <Text key={`${key}-c${i}`} color="#50FA7B" backgroundColor="#282A36"> {codeMatch[2]} </Text>
      );
      i++;
      remaining = codeMatch[3];
    } else {
      parts.push(<Text key={`${key}-t${i}`} color="#F8F8F2">{remaining}</Text>);
      break;
    }
  }

  return <Box key={String(key)} flexDirection="row" flexWrap="wrap">{parts}</Box>;
}

// ── Block renderer ────────────────────────────────────────────────────────────

const MarkdownText: React.FC<MarkdownTextProps> = ({ text }) => {
  const lines = text.split('\n');
  const elements: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // ── Fenced code block ─────────────────────────────────────────────────
    if (line.trimStart().startsWith('```')) {
      const lang = line.replace(/^```/, '').trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trimStart().startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      i++; // skip closing ```
      elements.push(
        <Box
          key={`code-${i}`}
          flexDirection="column"
          borderStyle="single"
          borderColor="#44475A"
          paddingX={1}
          marginY={1}
        >
          {lang ? (
            <Text color="#6272A4" dimColor>{lang}</Text>
          ) : null}
          {codeLines.map((cl, ci) => (
            <Text key={ci} color="#50FA7B">{cl}</Text>
          ))}
        </Box>
      );
      continue;
    }

    // ── Heading ───────────────────────────────────────────────────────────
    const headingMatch = line.match(/^(#{1,3})\s+(.+)/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const headingText = headingMatch[2];
      const color = level === 1 ? '#BD93F9' : level === 2 ? '#8BE9FD' : '#F1FA8C';
      elements.push(
        <Box key={`h-${i}`} marginTop={1} marginBottom={0}>
          <Text color={color} bold underline>{headingText}</Text>
        </Box>
      );
      i++;
      continue;
    }

    // ── Unordered list item ───────────────────────────────────────────────
    const ulMatch = line.match(/^(\s*)[*\-]\s+(.+)/);
    if (ulMatch) {
      const indent = ulMatch[1].length;
      elements.push(
        <Box key={`ul-${i}`} marginLeft={indent > 0 ? 4 : 2} flexDirection="row">
          <Text color="#FF79C6">• </Text>
          {renderInline(ulMatch[2], `ul-inline-${i}`)}
        </Box>
      );
      i++;
      continue;
    }

    // ── Ordered list item ─────────────────────────────────────────────────
    const olMatch = line.match(/^(\s*)\d+\.\s+(.+)/);
    if (olMatch) {
      const numPart = line.match(/^(\s*)(\d+)\./);
      const num = numPart ? numPart[2] : '1';
      const indent = olMatch[1].length;
      elements.push(
        <Box key={`ol-${i}`} marginLeft={indent > 0 ? 4 : 2} flexDirection="row">
          <Text color="#FFB86C">{num}. </Text>
          {renderInline(olMatch[2], `ol-inline-${i}`)}
        </Box>
      );
      i++;
      continue;
    }

    // ── Blockquote ────────────────────────────────────────────────────────
    const quoteMatch = line.match(/^>\s+(.+)/);
    if (quoteMatch) {
      elements.push(
        <Box
          key={`quote-${i}`}
          marginLeft={2}
          borderStyle="single"
          borderTop={false}
          borderBottom={false}
          borderRight={false}
          borderLeft
          borderColor="#6272A4"
          paddingLeft={1}
        >
          {renderInline(quoteMatch[1], `quote-inline-${i}`)}
        </Box>
      );
      i++;
      continue;
    }

    // ── Horizontal rule ───────────────────────────────────────────────────
    if (/^[-─*]{3,}$/.test(line.trim())) {
      elements.push(
        <Box key={`hr-${i}`} marginY={1}>
          <Text color="#44475A">{'─'.repeat(60)}</Text>
        </Box>
      );
      i++;
      continue;
    }

    // ── Empty line → vertical space ───────────────────────────────────────
    if (line.trim() === '') {
      elements.push(<Box key={`empty-${i}`} marginBottom={0}><Text>{' '}</Text></Box>);
      i++;
      continue;
    }

    // ── Plain text with inline formatting ─────────────────────────────────
    elements.push(
      <Box key={`p-${i}`} flexDirection="row" flexWrap="wrap">
        {renderInline(line, `p-inline-${i}`)}
      </Box>
    );
    i++;
  }

  return <Box flexDirection="column">{elements}</Box>;
};

export default MarkdownText;
