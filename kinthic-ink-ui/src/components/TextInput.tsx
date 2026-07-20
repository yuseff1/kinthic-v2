// ─────────────────────────────────────────────────────────────────────────────
// src/components/TextInput.tsx
// Custom, stable, horizontal-scrolling text input component for React Ink.
//
// Features:
//   • History navigation via up/down arrows (in-memory + session_history prop)
//   • Shift+Enter inserts a literal newline (multi-line support)
//   • No character cap (was 500 — removed)
//   • 3-node render: [before-cursor | cursor-char | after-cursor]
// ─────────────────────────────────────────────────────────────────────────────

import React, { useState, useEffect } from 'react';
import { Box, Text, useInput, useStdout, useStdin } from 'ink';
import { colors } from '../theme.js';
import CommandPalette, { type CommandSpec } from './CommandPalette.js';

interface TextInputProps {
  isActive?: boolean;
  /** Incremented by parent on each successful submit — clears local input. */
  resetToken?: number;
  onSubmit: (value: string) => void;
  placeholder?: string;
  commands?: CommandSpec[];
  /** Shell command history from ~/.kinthic/history, newest-last. */
  history?: string[];
}

const TextInput: React.FC<TextInputProps> = ({
  isActive = true,
  resetToken = 0,
  onSubmit,
  placeholder = '',
  commands = [],
  history = [],
}) => {
  const { stdout } = useStdout();
  const { internal_eventEmitter } = useStdin() as { internal_eventEmitter?: { prependListener: Function; removeListener: Function } };
  const lastKeyRef = React.useRef<string>('');

  useEffect(() => {
    if (!internal_eventEmitter) return;
    const handleInput = (chunk: string | Buffer) => {
      lastKeyRef.current = chunk.toString();
    };
    internal_eventEmitter.prependListener('input', handleInput);
    return () => {
      internal_eventEmitter.removeListener('input', handleInput);
    };
  }, [internal_eventEmitter]);

  const [value, setValue] = useState('');
  const [cursor, setCursor] = useState(0);
  const [startIndex, setStartIndex] = useState(0);

  // History navigation state
  // historyIndex == -1  → editing current draft
  // historyIndex >= 0   → browsing history[history.length - 1 - historyIndex]
  const [historyIndex, setHistoryIndex] = useState(-1);
  const [savedDraft, setSavedDraft] = useState('');
  const [paletteIndex, setPaletteIndex] = useState(0);
  const [paletteOpen, setPaletteOpen] = useState(true);

  // Clear input when parent signals a completed submit
  useEffect(() => {
    setValue('');
    setCursor(0);
    setStartIndex(0);
    setHistoryIndex(-1);
    setSavedDraft('');
    setPaletteIndex(0);
    setPaletteOpen(true);
  }, [resetToken]);

  const suggestions = React.useMemo(() => {
    if (!isActive || !paletteOpen || !value.startsWith('/') || !commands?.length) return [];
    const lower = value.toLowerCase().trim();
    return commands
      .map(c => {
        const haystack = `${c.cmd} ${c.args} ${c.desc}`.toLowerCase();
        const exact = c.cmd.toLowerCase().startsWith(lower) ? 3 : 0;
        const fuzzy = haystack.includes(lower.slice(1)) ? 1 : 0;
        return { command: c, score: exact + fuzzy };
      })
      .filter(item => item.score > 0 || lower === '/')
      .sort((a, b) => b.score - a.score || a.command.cmd.localeCompare(b.command.cmd))
      .map(item => item.command)
      .slice(0, 6);
  }, [value, commands, isActive, paletteOpen]);

  useEffect(() => {
    setPaletteIndex(0);
    if (value.startsWith('/')) setPaletteOpen(true);
  }, [value]);

  const columns = stdout?.columns ?? 80;
  const displayWidth = Math.max(10, columns - 24);

  useEffect(() => {
    setStartIndex(prev => {
      let start = prev;
      if (cursor < start) {
        start = cursor;
      } else if (cursor > start + displayWidth) {
        start = cursor - displayWidth;
      }
      if (start > value.length - displayWidth) {
        start = Math.max(0, value.length - displayWidth);
      }
      return start;
    });
  }, [cursor, value.length, displayWidth]);

  useInput((input, key) => {
    if (!isActive) return;

    const rawKey = lastKeyRef.current;

    // ── Shift+Enter → insert newline ────────────────────────────────────────
    // Ink reports Shift+Enter as input='\r' with key.shift=true on some
    // terminals, or as the escape sequence '\x1b[27;2;13~' on others.
    const isShiftEnter =
      (key.return && key.shift) ||
      rawKey === '\x1b[27;2;13~' ||
      rawKey === '\x1b[13;2u';

    if (isShiftEnter) {
      const newValue = value.slice(0, cursor) + '\n' + value.slice(cursor);
      setValue(newValue);
      setCursor(cursor + 1);
      return;
    }

    // ── Escape → close command palette without cancelling the turn ──────────
    if (key.escape && suggestions.length > 0) {
      setPaletteOpen(false);
      return;
    }

    // ── Plain Enter → accept palette command or submit ──────────────────────
    if (key.return) {
      if (suggestions.length > 0) {
        const selected = suggestions[Math.min(paletteIndex, suggestions.length - 1)];
        const completed = selected.cmd + (selected.args ? ' ' : '');
        setValue(completed);
        setCursor(completed.length);
        setPaletteOpen(false);
        return;
      }
      const trimmed = value.trim();
      if (trimmed) {
        onSubmit(trimmed);
      }
      return;
    }

    // ── Tab → autocomplete ──────────────────────────────────────────────────
    if (key.tab && suggestions.length > 0) {
      const selected = suggestions[Math.min(paletteIndex, suggestions.length - 1)];
      const completed = selected.cmd + (selected.args ? ' ' : '');
      setValue(completed);
      setCursor(completed.length);
      setHistoryIndex(-1);
      setPaletteOpen(false);
      return;
    }

    // ── Up arrow → palette selection or older history ───────────────────────
    if (key.upArrow) {
      if (suggestions.length > 0) {
        setPaletteIndex(prev => (prev <= 0 ? suggestions.length - 1 : prev - 1));
        return;
      }
      if (history.length === 0) return;
      const nextIdx = historyIndex + 1;
      if (nextIdx >= history.length) return;

      if (historyIndex === -1) {
        setSavedDraft(value);
      }
      setHistoryIndex(nextIdx);
      const entry = history[history.length - 1 - nextIdx];
      setValue(entry);
      setCursor(entry.length);
      return;
    }

    // ── Down arrow → palette selection or newer history / restore draft ─────
    if (key.downArrow) {
      if (suggestions.length > 0) {
        setPaletteIndex(prev => (prev + 1) % suggestions.length);
        return;
      }
      if (historyIndex <= 0) {
        setHistoryIndex(-1);
        const draft = historyIndex === 0 ? savedDraft : value;
        setValue(draft);
        setCursor(draft.length);
        return;
      }
      const nextIdx = historyIndex - 1;
      setHistoryIndex(nextIdx);
      const entry = history[history.length - 1 - nextIdx];
      setValue(entry);
      setCursor(entry.length);
      return;
    }

    // ── Backspace ───────────────────────────────────────────────────────────
    if (key.backspace) {
      if (cursor > 0) {
        const newValue = value.slice(0, cursor - 1) + value.slice(cursor);
        setValue(newValue);
        setCursor(cursor - 1);
      }
      return;
    }

    // ── Delete ──────────────────────────────────────────────────────────────
    if (key.delete) {
      const raw = lastKeyRef.current;
      if (raw === '\x7f' || raw === '\x08' || raw === '\b') {
        if (cursor > 0) {
          const newValue = value.slice(0, cursor - 1) + value.slice(cursor);
          setValue(newValue);
          setCursor(cursor - 1);
        }
      } else if (cursor < value.length) {
        const newValue = value.slice(0, cursor) + value.slice(cursor + 1);
        setValue(newValue);
      }
      return;
    }

    // ── Left / Right ────────────────────────────────────────────────────────
    if (key.leftArrow) {
      if (cursor > 0) setCursor(cursor - 1);
      return;
    }

    if (key.rightArrow) {
      if (cursor < value.length) setCursor(cursor + 1);
      return;
    }

    // ── Ctrl+A / Ctrl+E ─────────────────────────────────────────────────────
    if (input === '\u0001') {
      setCursor(0);
      return;
    }

    if (input === '\u0005') {
      setCursor(value.length);
      return;
    }

    // ── Regular character input (no char cap) ────────────────────────────────
    if (input && input.length >= 1 && !key.ctrl && !key.meta && !input.includes('\x1b')) {
      const newValue = value.slice(0, cursor) + input + value.slice(cursor);
      setValue(newValue);
      setCursor(cursor + input.length);
      if (historyIndex !== -1) {
        setHistoryIndex(-1);
      }
    }
  }, { isActive });

  if (!isActive) {
    return (
      <Box flexDirection="row">
        <Text color={colors.dimWhite} dimColor> </Text>
      </Box>
    );
  }
  if (value.length === 0) {
    return (
      <Box flexDirection="column">
        <Box flexDirection="row">
          <Text inverse color={colors.white}> </Text>
          <Text color={colors.dimWhite} dimColor>{placeholder}</Text>
        </Box>
        {suggestions.length > 0 && (
          <CommandPalette
            query={value}
            commands={suggestions}
            selectedIndex={Math.min(paletteIndex, suggestions.length - 1)}
          />
        )}
      </Box>
    );
  }

  const lines = value.split('\n');
  let currentLineIdx = 0;
  let cursorRemaining = cursor;
  for (let i = 0; i < lines.length; i++) {
    const lineLen = lines[i].length + 1;
    if (cursorRemaining < lineLen || i === lines.length - 1) {
      currentLineIdx = i;
      break;
    }
    cursorRemaining -= lineLen;
  }

  const activeLine = lines[currentLineIdx];
  const activeCursor = cursorRemaining;

  let start = startIndex;
  if (activeCursor < start) {
    start = activeCursor;
  } else if (activeCursor >= start + displayWidth) {
    start = activeCursor - displayWidth + 1;
  }
  if (start > Math.max(0, activeLine.length - displayWidth + 1)) {
    start = Math.max(0, activeLine.length - displayWidth + 1);
  }

  const visibleSlice = activeLine.slice(start, start + displayWidth);
  const cursorIndexInSlice = activeCursor - start;

  const beforeCursor = visibleSlice.slice(0, cursorIndexInSlice);
  const atCursor = cursorIndexInSlice < visibleSlice.length ? visibleSlice[cursorIndexInSlice] : ' ';
  const afterCursor = cursorIndexInSlice < visibleSlice.length ? visibleSlice.slice(cursorIndexInSlice + 1) : '';

  return (
    <Box flexDirection="column">
      {lines.map((line, idx) => {
        if (idx === currentLineIdx) {
          return (
            <Box key={idx} flexDirection="row">
              {beforeCursor.length > 0 && <Text color={colors.white}>{beforeCursor}</Text>}
              <Text inverse color={colors.white}>{atCursor}</Text>
              {afterCursor.length > 0 && <Text color={colors.white}>{afterCursor}</Text>}
            </Box>
          );
        }
        return (
          <Box key={idx} flexDirection="row">
            <Text color={colors.white}>{line}</Text>
          </Box>
        );
      })}
      {suggestions.length > 0 && (
        <CommandPalette
          query={value}
          commands={suggestions}
          selectedIndex={Math.min(paletteIndex, suggestions.length - 1)}
        />
      )}
    </Box>
  );
};

export default TextInput;
