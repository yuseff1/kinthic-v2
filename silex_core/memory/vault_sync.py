import asyncio
import hashlib
import os
import re
import time
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from silex_core.utils.logger import setup_logger
from silex_core.utils.config import KINTHIC_HOME

log = setup_logger("silex.vault_sync")


def get_heuristic_title(content: str, node_id: str) -> str:
    """Generates a clean Obsidian filename from content and UUID."""
    # Take first ~40 chars, keep only alphanumerics and spaces
    clean = re.sub(r"[^\w\s]", "", content)
    words = clean.split()[:5]
    if not words:
        return f"node_{node_id[:8]}"
    title = "_".join(words)
    return f"{title}_{node_id[:6]}"


def compute_node_hash(content: str, status: str, ntype: str) -> str:
    return hashlib.sha256(f"{content}:{status}:{ntype}".encode()).hexdigest()


class VaultEventHandler(FileSystemEventHandler):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def _is_markdown(self, path: str) -> bool:
        return path.endswith(".md")

    def on_modified(self, event: FileSystemEvent):
        if not event.is_directory and self._is_markdown(event.src_path):
            self.callback(event.src_path, "modified")

    def on_created(self, event: FileSystemEvent):
        if not event.is_directory and self._is_markdown(event.src_path):
            self.callback(event.src_path, "created")

    def on_moved(self, event: FileSystemEvent):
        if not event.is_directory and self._is_markdown(event.dest_path):
            self.callback(event.dest_path, "modified")


class VaultSyncWorker:
    def __init__(self, db, vault_dir: Path, debounce_seconds: float = 5.0):
        self.db = db
        self.vault_dir = vault_dir
        self.debounce_seconds = debounce_seconds
        self.pending_events: dict[str, float] = {}
        self.observer = None

    def _on_fs_event(self, filepath: str, action: str):
        self.pending_events[filepath] = time.time()

    async def _process_fs_events(self):
        """Syncs modified markdown files from Obsidian back to SQLite."""
        now = time.time()
        to_process = []
        for fp, t in list(self.pending_events.items()):
            if now - t > self.debounce_seconds:
                to_process.append(fp)
                del self.pending_events[fp]

        for fp in to_process:
            path = Path(fp)
            if not path.exists():
                continue

            try:
                content_text = path.read_text(encoding="utf-8")
                
                # Simple frontmatter parser
                if not content_text.startswith("---\n"):
                    continue
                    
                parts = content_text.split("---\n", 2)
                if len(parts) < 3:
                    continue
                    
                frontmatter = parts[1]
                body = parts[2].strip()
                
                kinthic_id = None
                for line in frontmatter.splitlines():
                    if line.startswith("kinthic_id:"):
                        kinthic_id = line.split(":", 1)[1].strip()
                        break
                        
                if not kinthic_id:
                    continue
                    
                # Fetch node from DB to check if actually changed
                node = await self.db.fetch_one("SELECT * FROM epistemic_nodes WHERE node_id = ?", (kinthic_id,))
                if not node:
                    continue
                    
                new_hash = compute_node_hash(body, node["status"], node["type"])
                sync_state = await self.db.fetch_one("SELECT last_hash FROM vault_sync_state WHERE node_id = ?", (kinthic_id,))
                
                if not sync_state or sync_state["last_hash"] != new_hash:
                    # Update the database!
                    # Calculate new integrity_hash for the updated node
                    new_integrity_hash = hashlib.sha256(
                        f"{node['type']}|{body}|{node['provenance']}|{node['timestamp']}".encode("utf-8")
                    ).hexdigest()
                    
                    await self.db.execute(
                        "UPDATE epistemic_nodes SET content = ?, integrity_hash = ? WHERE node_id = ?", 
                        (body, new_integrity_hash, kinthic_id)
                    )
                    await self.db.execute(
                        "INSERT OR REPLACE INTO vault_sync_state (node_id, last_hash, synced_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                        (kinthic_id, new_hash)
                    )
                    log.info(f"Obsidian->DB Sync: Updated node {kinthic_id[:8]} from file {path.name}")
                    
                    # (Future enhancement: parse [[WikiLinks]] here and update epistemic_edges)

            except Exception as e:
                log.error(f"Error syncing {path.name} to DB: {e}")

    async def _sync_db_to_vault(self):
        """Syncs nodes from SQLite to Obsidian Markdown files."""
        try:
            nodes = await self.db.fetch_all("SELECT * FROM epistemic_nodes")
            for node in nodes:
                node_id = node["node_id"]
                content = node["content"]
                status = node["status"]
                ntype = node["type"]
                timestamp = node["timestamp"]
                
                current_hash = compute_node_hash(content, status, ntype)
                
                sync_state = await self.db.fetch_one("SELECT last_hash FROM vault_sync_state WHERE node_id = ?", (node_id,))
                if sync_state and sync_state["last_hash"] == current_hash:
                    continue # Already in sync
                    
                # Needs sync!
                title = get_heuristic_title(content, node_id)
                filepath = self.vault_dir / f"{title}.md"
                
                # Fetch edges
                edges = await self.db.fetch_all("SELECT target_node_id, relation_type FROM epistemic_edges WHERE source_node_id = ?", (node_id,))
                
                # Resolve target node titles for wiki links
                links_text = ""
                if edges:
                    links_text = "\n\n## Relationships\n"
                    for edge in edges:
                        target = await self.db.fetch_one("SELECT content, node_id FROM epistemic_nodes WHERE node_id = ?", (edge["target_node_id"],))
                        if target:
                            target_title = get_heuristic_title(target["content"], target["node_id"])
                            links_text += f"- [[{target_title}]] ({edge['relation_type']})\n"
                
                # Build markdown
                md = f"---\nkinthic_id: {node_id}\ntype: {ntype}\nstatus: {status}\ntimestamp: {timestamp}\n---\n\n{content}{links_text}"
                
                # Write to file
                filepath.write_text(md, encoding="utf-8")
                
                # Update sync state
                await self.db.execute(
                    "INSERT OR REPLACE INTO vault_sync_state (node_id, last_hash, synced_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                    (node_id, current_hash)
                )
                log.debug(f"DB->Obsidian Sync: Exported node {node_id[:8]} to {filepath.name}")
                
        except Exception as e:
            log.error(f"Error in DB->Obsidian sync: {e}")

    async def run_loop(self):
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        
        # Start file watcher
        handler = VaultEventHandler(self._on_fs_event)
        self.observer = Observer()
        self.observer.schedule(handler, str(self.vault_dir), recursive=False)
        self.observer.start()
        
        log.info(f"Vault Sync Worker started on {self.vault_dir}")
        
        backoff = 0.0
        try:
            while True:
                try:
                    await self._process_fs_events()
                    await self._sync_db_to_vault()
                    await asyncio.sleep(2.0)
                    backoff = 0.0
                except Exception as e:
                    backoff = min(60.0, max(2.0, backoff * 2))
                    log.error(f"Vault Sync error: {e}. Retrying in {backoff}s...")
                    await asyncio.sleep(backoff)
        except asyncio.CancelledError:
            self.observer.stop()
            self.observer.join()
            log.info("Vault Sync Worker gracefully shut down.")
