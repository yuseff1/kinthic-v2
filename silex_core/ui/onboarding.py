"""
silex/ui/onboarding.py
======================
Zero-dependency raw-ANSI interactive TUI for the Kinthic setup wizard.

Architecture mirrors a reactive Widget pattern:
  - ProviderSelector  – stateful interactive list (like a Textual Widget)
  - OnboardingUI      – top-level session coordinator (clear, render, prompt)

Design spec (matches Hermes reference image exactly):
  Header 1 : "Select provider:"          → bold amber  \033[1;33m
  Header 2 : "  ↑↓ navigate …"           → dim gray    \033[2m
  Selected : "→ (•) Label (desc)"         → green       \033[32m
  Default  : "  (O) Label (desc)"         → normal      (no colour code)

All redraws are done in-place via ANSI cursor movement so the frame
never scrolls — absolute zero scrolling.
"""

from __future__ import annotations

import sys
import os
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# ANSI helpers
# ─────────────────────────────────────────────────────────────────────────────

_AMBER = "\033[1;33m"  # bold yellow/amber – header
_DIM = "\033[2m"  # dim   – legend / unselected text
_GREEN = "\033[32m"  # green – active row
_RED = "\033[1;31m"  # bold red – error messages
_WHITE = "\033[1;37m"  # bold white – prompts / info
_RESET = "\033[0m"


def _ansi_enable_win32() -> None:
    """Enable VT-100 processing on Windows Console Host."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        hOut = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        if hOut and hOut != -1:
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(hOut, ctypes.byref(mode)):
                kernel32.SetConsoleMode(hOut, mode.value | 0x0004)
    except Exception:
        pass


def _write(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()


def _clear_screen() -> None:
    """Full terminal clear (cls / clear)."""
    if sys.platform == "win32":
        os.system("cls")
    else:
        _write("\033[H\033[J")


# ─────────────────────────────────────────────────────────────────────────────
# Cross-platform single-key reader
# ─────────────────────────────────────────────────────────────────────────────


def _get_key() -> str:
    """Read one logical keypress and return a named string token."""
    if sys.platform == "win32":
        import msvcrt

        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):  # extended key prefix
            ch2 = msvcrt.getch()
            if ch2 == b"H":
                return "up"
            if ch2 == b"P":
                return "down"
            if ch2 == b"K":
                return "left"
            if ch2 == b"M":
                return "right"
            return ""
        if ch in (b"\r", b"\n"):
            return "enter"
        if ch == b" ":
            return "space"
        if ch == b"\x1b":
            return "escape"
        if ch == b"\x03":
            raise KeyboardInterrupt
        if ch == b"\x08":
            return "backspace"
        try:
            return ch.decode("utf-8").lower()
        except Exception:
            return ""
    else:
        import tty
        import termios
        import select

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = os.read(fd, 1)
            if ch == b"\x1b":
                r, _, _ = select.select([fd], [], [], 0.15)
                if r:
                    ch2 = os.read(fd, 1)
                    if ch2 == b"[":
                        ch3 = os.read(fd, 1)
                        if ch3 == b"A":
                            return "up"
                        if ch3 == b"B":
                            return "down"
                        if ch3 == b"C":
                            return "right"
                        if ch3 == b"D":
                            return "left"
                return "escape"
            if ch in (b"\r", b"\n"):
                return "enter"
            if ch == b" ":
                return "space"
            if ch == b"\x03":
                raise KeyboardInterrupt
            if ch in (b"\x7f", b"\x08"):
                return "backspace"
            return ch.decode("utf-8", errors="ignore").lower()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


# ─────────────────────────────────────────────────────────────────────────────
# ProviderSelector — reactive Widget (pure-ANSI, zero-dep)
# ─────────────────────────────────────────────────────────────────────────────


class ProviderSelector:
    """
    Interactive provider-list widget.

    Behaves exactly like a Textual reactive Widget:
      - `current_index` is the reactive integer pointer.
      - `render()` assembles the full frame string from scratch.
      - `on_key()` mutates `current_index` and re-renders in-place.
      - `run()` is the blocking event loop; returns the selected index.

    Visual spec (matches reference image pixel-for-pixel):

        Select provider:
          ↑↓ navigate   ENTER/SPACE select   ESC cancel

        → (•) Google Gemini (Google AI Studio Gemini Models)
          (O) Anthropic (Anthropic Claude Models)
          (O) OpenAI
          ...
    """

    # ── Public state (reactive analogue) ──────────────────────────────────
    current_index: int = 0

    def __init__(
        self,
        title: str,
        choices: list[str],
        default_idx: int = 0,
    ) -> None:
        self.title = title
        self.choices = choices
        self.current_index = max(0, min(default_idx, len(choices) - 1))
        self._lines_rendered = 0  # tracks how many lines last drawn

    # ── render() — assembles full frame ───────────────────────────────────

    def render(self) -> str:
        """
        Build the complete frame string.
        Mirrors Widget.render() → RenderableType in Textual.
        """
        lines: list[str] = []

        # Header line 1 — bold amber
        lines.append(f"{_AMBER}{self.title}{_RESET}")

        # Header line 2 — dim legend
        lines.append(
            f"{_DIM}  \u2191\u2193 navigate   ENTER/SPACE select   ESC cancel{_RESET}"
        )

        # Empty spacer
        lines.append("")

        # Choice rows
        for i, choice in enumerate(self.choices):
            if i == self.current_index:
                # Active: green arrow + filled bullet
                lines.append(f"{_GREEN}\u2192 (\u2022) {choice}{_RESET}")
            else:
                # Inactive: plain empty circle (no colour codes — matches image)
                lines.append(f"  (O) {choice}")

        return "\n".join(lines)

    # ── In-place redraw ───────────────────────────────────────────────────

    def _draw(self) -> None:
        """Redraw the frame in-place (zero-scroll)."""
        frame = self.render()
        new_lines = frame.count("\n") + 1

        if self._lines_rendered > 0:
            # Move cursor up to top of frame, then erase to end of screen
            _write(f"\033[{self._lines_rendered}A\033[J")

        _write(frame + "\n")
        self._lines_rendered = new_lines

    # ── on_key() — Textual-style keyboard handler ─────────────────────────

    def on_key(self, key: str) -> str | None:
        """
        Process one key event.
        Returns:
          "selected" when Enter/Space is pressed.
          "cancelled" when Escape is pressed.
          None       to continue the event loop.
        """
        if key == "up":
            self.current_index = max(0, self.current_index - 1)
        elif key == "down":
            self.current_index = min(len(self.choices) - 1, self.current_index + 1)
        elif key in ("enter", "space"):
            return "selected"
        elif key == "escape":
            return "cancelled"
        return None

    # ── run() — blocking event loop ───────────────────────────────────────

    def run(self) -> int:
        """
        Blocking interactive loop.
        Returns the chosen index (clamped to valid range).

        Falls back to numbered prompt if stdin is not a TTY.
        """
        if not sys.stdin.isatty():
            return self._fallback_numbered()

        _ansi_enable_win32()
        _write("\033[?25l")  # hide cursor

        try:
            self._draw()  # initial render

            while True:
                try:
                    key = _get_key()
                except KeyboardInterrupt:
                    _write("\033[?25h\n")
                    raise

                action = self.on_key(key)

                if action == "selected":
                    return self.current_index
                elif action == "cancelled":
                    raise KeyboardInterrupt("Cancelled by user")
                else:
                    # Reactive re-render (state changed → repaint)
                    self._draw()
        finally:
            _write("\033[?25h")  # restore cursor

    # ── Fallback: non-TTY numbered prompt ─────────────────────────────────

    def _fallback_numbered(self) -> int:
        """Simple numbered prompt for non-interactive environments."""
        print(f"\n{self.title}\n")
        for i, choice in enumerate(self.choices, 1):
            prefix = "→" if i - 1 == self.current_index else " "
            print(f"  {prefix} {i}. {choice}")
        raw = input(
            f"\nSelect [1-{len(self.choices)}] (default {self.current_index + 1}): "
        ).strip()
        try:
            idx = int(raw) - 1
            return max(0, min(len(self.choices) - 1, idx))
        except (ValueError, TypeError):
            return self.current_index


# ─────────────────────────────────────────────────────────────────────────────
# OnboardingUI — session coordinator
# ─────────────────────────────────────────────────────────────────────────────


class OnboardingUI:
    """
    Top-level session orchestrator for the Kinthic setup wizard.

    Provides:
      - clear()          — wipe terminal
      - render_step()    — print a titled info screen
      - prompt_choice()  — delegate to ProviderSelector.run()
      - prompt()         — styled text input
      - prompt_password()— char-by-char green asterisk masking
    """

    def __init__(self) -> None:
        _ansi_enable_win32()

    # ── Screen management ─────────────────────────────────────────────────

    def clear(self) -> None:
        """Clear the terminal screen."""
        _clear_screen()

    # ── Step renderer ─────────────────────────────────────────────────────

    def render_step(
        self,
        title: str,
        content: Any,
        subtitle: str | None = None,
    ) -> None:
        """
        Print a titled info frame (borderless, in-place cleared).
        `content` can be a string, or any object with a __str__ method
        (including Rich Text/Renderables — we call str() on them).
        """
        _clear_screen()

        lines: list[str] = []
        lines.append(f"{_AMBER}{title.upper()}{_RESET}")
        lines.append("")

        # Handle Rich Text / renderables gracefully
        content_str = str(content) if not isinstance(content, str) else content
        # Strip Rich markup tags for plain display
        import re

        content_str = re.sub(r"\[/?[^\]]+\]", "", content_str)
        lines.append(f"  {content_str}")

        if subtitle:
            lines.append("")
            lines.append(f"{_DIM}  {subtitle}{_RESET}")

        lines.append("")
        _write("\n".join(lines) + "\n")

    # ── Interactive choice selector ───────────────────────────────────────

    def prompt_choice(
        self,
        title: str,
        choices: list[str],
        default_idx: int = 0,
        subtitle: str | None = None,
    ) -> int:
        """
        Present an interactive list using ProviderSelector.
        The `subtitle` is shown as the header title for flavour.
        Returns the index of the selected choice.
        """
        _clear_screen()

        # Use title if no subtitle, else use title as header
        display_title = f"Select {title.lower()}:"
        selector = ProviderSelector(
            title=display_title,
            choices=choices,
            default_idx=default_idx,
        )
        return selector.run()

    # ── Text prompt ───────────────────────────────────────────────────────

    def prompt(self, text: str, default: str = "", password: bool = False) -> str:
        """Styled inline text prompt."""
        if password:
            return self.prompt_password(text) or default
        _write(f"{_WHITE}  > {text}: {_RESET}")
        sys.stdout.flush()
        try:
            val = sys.stdin.readline().strip()
        except (EOFError, KeyboardInterrupt):
            val = ""
        return val or default

    # ── Password prompt with green asterisk masking ───────────────────────

    def prompt_password(self, text: str) -> str:
        """
        Character-by-character password entry.
        Each typed/pasted character is shown as a green asterisk *.
        Backspace removes the last asterisk.
        Works on both Windows (msvcrt) and Unix (raw tty).
        """
        _write(f"{_WHITE}  > {text}: {_RESET}")
        sys.stdout.flush()

        if not sys.stdin.isatty():
            import getpass

            try:
                return getpass.getpass("").strip()
            except Exception:
                return sys.stdin.readline().strip()

        buf: list[str] = []

        try:
            if sys.platform == "win32":
                import msvcrt

                while True:
                    ch = msvcrt.getch()
                    if ch in (b"\x00", b"\xe0"):  # skip arrow key sequences
                        msvcrt.getch()
                        continue
                    if ch in (b"\r", b"\n"):
                        _write("\n")
                        break
                    elif ch == b"\x08":  # backspace
                        if buf:
                            buf.pop()
                            _write("\b \b")
                    elif ch == b"\x03":
                        raise KeyboardInterrupt
                    elif ch == b"\x1b":
                        pass  # ignore ESC
                    else:
                        try:
                            c = ch.decode("utf-8")
                            if c.isprintable():
                                buf.append(c)
                                _write(f"{_GREEN}*{_RESET}")
                        except Exception:
                            pass
            else:
                import tty
                import termios

                fd = sys.stdin.fileno()
                old = termios.tcgetattr(fd)
                try:
                    tty.setraw(fd)
                    while True:
                        ch = sys.stdin.read(1)
                        if ch in ("\r", "\n"):
                            _write("\r\n")
                            break
                        elif ch in ("\x7f", "\x08"):  # backspace
                            if buf:
                                buf.pop()
                                _write("\b \b")
                        elif ch == "\x03":
                            raise KeyboardInterrupt
                        elif ch == "\x1b":
                            pass
                        else:
                            if ch.isprintable():
                                buf.append(ch)
                                _write(f"{_GREEN}*{_RESET}")
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except KeyboardInterrupt:
            _write("\n")
            raise

        return "".join(buf).strip()
