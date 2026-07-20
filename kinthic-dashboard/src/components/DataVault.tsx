"use client";

import { useCallback, useEffect, useState } from "react";
import { CloudUploadIcon, DatabaseSyncIcon, FloppyDiskIcon, RefreshIcon } from "hugeicons-react";
import { apiFetch } from "@/lib/api";

type Backup = {
  name: string;
  path: string;
  size_bytes: number;
  modified_at: string;
};

type RestorePreview = {
  valid?: boolean;
  file_count?: number;
  restore_file_count?: number;
  warnings?: string[];
  errors?: string[];
  sample_files?: string[];
  pre_backup_path?: string;
  restored_count?: number;
  message?: string;
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DataVault() {
  const [backups, setBackups] = useState<Backup[]>([]);
  const [backupDir, setBackupDir] = useState("");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [preview, setPreview] = useState<RestorePreview | null>(null);
  const [restoring, setRestoring] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const loadBackups = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiFetch("/api/backups");
      const data = await res.json();
      setBackups(data.backups || []);
      setBackupDir(data.backup_dir || "");
    } catch (err) {
      console.warn("Failed to load backups:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadBackups();
  }, [loadBackups]);

  const handleCreateBackup = async () => {
    setCreating(true);
    setStatus(null);
    try {
      const res = await apiFetch("/api/backups", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Backup failed");
      setStatus(`Backup created: ${data.name}`);
      await loadBackups();
    } catch (err: any) {
      setStatus(err.message || "Backup failed");
    } finally {
      setCreating(false);
    }
  };

  const handlePreview = async (path: string) => {
    setSelected(path);
    setPreview(null);
    setStatus(null);
    try {
      const res = await apiFetch("/api/restore/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ archive: path }),
      });
      const data = await res.json();
      setPreview(data);
    } catch (err: any) {
      setStatus(err.message || "Preview failed");
    }
  };

  const handleRestore = async () => {
    if (!selected || !preview?.valid) return;
    if (!confirm("Restore will replace ~/.kinthic data. Continue?")) return;

    setRestoring(true);
    setStatus(null);
    try {
      const res = await apiFetch("/api/restore/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ archive: selected, pre_backup: true }),
      });
      const data = await res.json();
      if (!res.ok) {
        const detail = data.detail;
        const msg = typeof detail === "string" ? detail : detail?.message || JSON.stringify(detail);
        throw new Error(msg);
      }
      setStatus(data.message || "Restore complete. Restart kinthic web.");
      setPreview(null);
      await loadBackups();
    } catch (err: any) {
      setStatus(err.message || "Restore failed");
    } finally {
      setRestoring(false);
    }
  };

  return (
    <div className="h-full bg-canvas text-text-secondary p-6 overflow-y-auto">
      <div className="flex items-center justify-between gap-4 mb-6 border-b border-border-subtle pb-4">
        <div className="flex items-center gap-3 text-text-primary">
          <FloppyDiskIcon className="w-7 h-7 text-terracotta" />
          <div>
            <h2 className="text-xl font-display font-semibold tracking-wider text-text-primary uppercase">Data Vault</h2>
            <p className="text-xs text-text-secondary mt-1 font-serif">Backup and restore your Kinthic brain</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={loadBackups}
            className="p-2.5 rounded-lg bg-surface-1 border border-border-subtle hover:bg-surface-2 text-text-secondary hover:text-text-primary transition-colors"
            title="Refresh"
          >
            <RefreshIcon className="w-5 h-5" />
          </button>
          <button
            onClick={handleCreateBackup}
            disabled={creating}
            className="flex items-center gap-2 px-4 py-2.5 bg-terracotta text-background hover:opacity-90 rounded-lg font-display font-bold text-sm disabled:opacity-50 transition-all"
          >
            <CloudUploadIcon className="w-4 h-4" />
            {creating ? "Backing up..." : "Create Backup"}
          </button>
        </div>
      </div>

      {status && (
        <div className="mb-4 p-4 rounded-xl bg-sage/10 border border-sage/20 text-sm text-sage font-serif">
          {status}
        </div>
      )}

      {backupDir && (
        <p className="text-xs font-mono text-text-tertiary mb-4">Storage: {backupDir}</p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 max-w-5xl">
        <div>
          <h3 className="text-xs font-display font-semibold tracking-wider text-text-tertiary uppercase mb-3">Backups</h3>
          {loading ? (
            <div className="text-terracotta animate-pulse font-display">Loading...</div>
          ) : backups.length === 0 ? (
            <div className="p-6 border border-dashed border-border-subtle rounded-xl text-text-tertiary text-center text-sm font-serif">
              No backups yet. Create one to protect your memory store.
            </div>
          ) : (
            <div className="space-y-2">
              {backups.map((b) => (
                <button
                  key={b.path}
                  onClick={() => handlePreview(b.path)}
                  className={`w-full text-left p-4 rounded-xl border transition-all ${
                    selected === b.path
                      ? "bg-surface-1 border-border-strong text-terracotta"
                      : "bg-surface-2 border-border-subtle hover:border-border-strong"
                  }`}
                >
                  <div className={`font-display text-sm truncate font-semibold ${selected === b.path ? 'text-terracotta' : 'text-text-primary'}`}>{b.name}</div>
                  <div className="text-xs text-text-tertiary mt-1 font-serif">
                    {formatBytes(b.size_bytes)} · {new Date(b.modified_at).toLocaleString()}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        <div>
          <h3 className="text-xs font-display font-semibold tracking-wider text-text-tertiary uppercase mb-3">Restore Preview</h3>
          {!preview ? (
            <div className="p-6 border border-dashed border-border-subtle rounded-xl text-text-tertiary text-center text-sm font-serif">
              Select a backup to preview what will be restored.
            </div>
          ) : preview.errors?.length ? (
            <div className="p-4 rounded-xl bg-terracotta/5 border border-terracotta/30 text-terracotta text-sm space-y-1 font-serif">
              {preview.errors.map((e) => (
                <div key={e}>• {e}</div>
              ))}
            </div>
          ) : (
            <div className="bg-surface-1 border border-border-subtle rounded-xl p-5 space-y-4 card-frame">
              <div className="flex items-center gap-2 text-sage text-sm font-display font-semibold">
                <DatabaseSyncIcon className="w-4 h-4" />
                Valid backup — {preview.restore_file_count ?? preview.file_count} files to restore
              </div>
              {preview.warnings?.map((w) => (
                <div key={w} className="text-terracotta text-xs font-serif">⚠ {w}</div>
              ))}
              {preview.sample_files?.length ? (
                <div>
                  <div className="text-xs text-text-tertiary uppercase mb-2 font-display">Sample paths</div>
                  <ul className="text-xs font-mono text-text-secondary space-y-1">
                    {preview.sample_files.map((f) => (
                      <li key={f} className="truncate">• {f}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <p className="text-xs text-text-tertiary font-serif">
                secrets.json is never overwritten. A pre-restore safety backup is created automatically.
              </p>
              <button
                onClick={handleRestore}
                disabled={!preview.valid || restoring}
                className="w-full py-2.5 rounded-lg bg-terracotta/10 hover:bg-terracotta/20 text-terracotta border border-terracotta/20 font-display font-semibold text-sm disabled:opacity-40 transition-colors"
              >
                {restoring ? "Restoring..." : "Apply Restore"}
              </button>
              <p className="text-[10px] text-text-tertiary text-center font-serif">
                Stop the daemon first if running. Restart kinthic web after restore.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
