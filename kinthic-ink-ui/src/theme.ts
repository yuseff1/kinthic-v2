// ─────────────────────────────────────────────────────────────────────────────
// src/theme.ts — Centralized color constants for all Kinthic Ink components.
// ─────────────────────────────────────────────────────────────────────────────

export const colors = {
  /** Kinthic cyan — headers, ASCII art, accents */
  cyan: '#8BE9FD',
  /** Amber — warnings, tool auth emblem */
  amber: '#FFB86C',
  /** Success green — approval confirmations, diff additions */
  green: '#50FA7B',
  /** Danger red — rejections, diff removals */
  red: '#FF5555',
  /** Muted purple-grey — dim metadata text */
  dimWhite: '#6272A4',
  /** Bright white — primary label text */
  white: '#F8F8F2',
  /** Deep grey — separators, borders */
  separator: '#44475A',
  /** Prompt gold — interactive cursor prompt */
  prompt: '#F1FA8C',
  /** Kin Primary (Void Indigo) */
  primary: '#312e81',
} as const;

export const symbols = {
  /** Vertical panel divider */
  vbar: '│',
  /** Horizontal rule character */
  hbar: '─',
  /** Corner top-left */
  tl: '┌',
  /** Corner top-right */
  tr: '┐',
  /** Corner bottom-left */
  bl: '└',
  /** Corner bottom-right */
  br: '┘',
  /** T-junction right */
  tRight: '├',
  /** T-junction left */
  tLeft: '┤',
  /** Cross */
  cross: '┼',
  /** Spinner frames */
  spinner: ['⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏'],
  /** Success checkmark */
  check: '✔',
  /** Arrow right */
  arrow: '➔',
  /** Warning bolt */
  bolt: '⚡',
} as const;
