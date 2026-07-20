"""Watch ~/.kinthic/skills for changes and hot-reload."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

log = logging.getLogger("silex.core.skills_watcher")


class SkillsWatcher:
    """Reload skills when files change under skills directories."""

    def __init__(
        self,
        reload_callback: Callable[[], None],
        watch_paths: list[Path] | None = None,
    ) -> None:
        from silex_core.utils.config import KINTHIC_PLUGINS_SKILLS, KINTHIC_SKILLS

        self._callback = reload_callback
        self._watch_paths = watch_paths or [KINTHIC_SKILLS, KINTHIC_PLUGINS_SKILLS]
        self._observer = None
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:
            log.debug("watchdog not available; skills hot reload disabled")
            return

        watcher = self

        class _Handler(FileSystemEventHandler):
            def on_any_event(self, event):  # noqa: ANN001
                if event.is_directory:
                    return
                src = getattr(event, "src_path", "")
                if not src.endswith((".md", ".yaml", ".yml")):
                    return
                try:
                    watcher._callback()
                except Exception as exc:
                    log.warning("Skills reload failed: %s", exc)

        observer = Observer()
        handler = _Handler()
        for path in self._watch_paths:
            if path.exists():
                observer.schedule(handler, str(path), recursive=True)
        if not observer.emitters:
            return
        observer.daemon = True
        observer.start()
        self._observer = observer
        self._started = True
        log.info("Skills watcher started on %s", self._watch_paths)

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2)
            self._observer = None
        self._started = False


def start_skills_watcher(reload_callback: Callable[[], None]) -> SkillsWatcher | None:
    """Start background watcher; safe to call from cognitive loop startup."""
    watcher = SkillsWatcher(reload_callback)
    try:
        watcher.start()
        return watcher if watcher._started else None
    except Exception as exc:
        log.debug("Could not start skills watcher: %s", exc)
        return None
