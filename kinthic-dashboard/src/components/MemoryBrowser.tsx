"use client";

import { useCallback, useEffect, useState } from "react";
import { Database01Icon, Search01Icon, Delete02Icon } from "hugeicons-react";
import { apiFetch } from "@/lib/api";

type Memory = {
  id: string;
  content: string;
  importance: number;
  confidence: number;
  memory_type: string;
  tags: string[];
  created_at: string;
  access_count: number;
};

export default function MemoryBrowser() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const limit = 20;

  const loadMemories = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        offset: String(offset),
        limit: String(limit),
      });
      if (query) params.set("q", query);
      const res = await apiFetch(`/api/memories?${params}`);
      const data = await res.json();
      setMemories(data.memories || []);
      setTotal(data.total || 0);
    } catch (err) {
      console.warn("Failed to load memories:", err);
    } finally {
      setLoading(false);
    }
  }, [offset, query]);

  useEffect(() => {
    loadMemories();
  }, [loadMemories]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setOffset(0);
    setQuery(searchInput.trim());
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this memory permanently?")) return;
    setDeletingId(id);
    try {
      const res = await apiFetch(`/api/memories/${id}?confirm=true`, { method: "DELETE" });
      if (res.ok) {
        setMemories((prev) => prev.filter((m) => m.id !== id));
        setTotal((t) => Math.max(0, t - 1));
      }
    } catch (err) {
      console.error(err);
    } finally {
      setDeletingId(null);
    }
  };

  const page = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));

  return (
    <div className="h-full bg-canvas text-text-secondary p-6 overflow-y-auto">
      <div className="flex items-center gap-3 mb-6 text-text-primary border-b border-border-subtle pb-4">
        <Database01Icon className="w-7 h-7 text-terracotta" />
        <div>
          <h2 className="text-xl font-display font-semibold tracking-wider text-text-primary uppercase">Memory Browser</h2>
          <p className="text-xs text-text-secondary mt-1 font-serif">
            Search and inspect the Silex memory store ({total.toLocaleString()} total)
          </p>
        </div>
      </div>

      <form onSubmit={handleSearch} className="flex gap-2 mb-6 max-w-xl">
        <div className="relative flex-1">
          <Search01Icon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-tertiary" />
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search memories..."
            className="w-full bg-surface-1 border border-border-subtle rounded-lg pl-10 pr-4 py-2.5 text-text-primary text-sm focus:outline-none focus:border-terracotta transition-colors"
          />
        </div>
        <button
          type="submit"
          className="px-4 py-2.5 bg-surface-1 border border-border-subtle hover:bg-surface-2 rounded-lg text-sm font-display font-semibold text-text-primary transition-colors"
        >
          Search
        </button>
        {query && (
          <button
            type="button"
            onClick={() => { setQuery(""); setSearchInput(""); setOffset(0); }}
            className="px-4 py-2.5 text-text-secondary hover:text-text-primary text-sm font-display"
          >
            Clear
          </button>
        )}
      </form>

      {loading ? (
        <div className="text-terracotta animate-pulse font-display font-semibold">Loading memories...</div>
      ) : memories.length === 0 ? (
        <div className="text-text-tertiary italic p-8 border border-dashed border-border-subtle rounded-xl text-center font-serif">
          {query ? "No memories match your search." : "No memories stored yet."}
        </div>
      ) : (
        <div className="space-y-3 max-w-4xl">
          {memories.map((m) => (
            <div
              key={m.id}
              className="bg-surface-1 border border-border-subtle rounded-xl p-4 hover:border-border-strong transition-all duration-300 card-frame group"
            >
              <div className="flex justify-between gap-4">
                <p className="text-text-primary text-sm leading-relaxed flex-1 font-serif">{m.content}</p>
                <button
                  onClick={() => handleDelete(m.id)}
                  disabled={deletingId === m.id}
                  className="opacity-0 group-hover:opacity-100 p-2 text-text-tertiary hover:text-terracotta transition-all disabled:opacity-50"
                  title="Delete memory"
                >
                  <Delete02Icon className="w-4 h-4" />
                </button>
              </div>
              <div className="mt-3 flex flex-wrap gap-2 text-xs text-text-secondary font-serif">
                <span className="font-mono bg-surface-2 border border-border-subtle px-2 py-0.5 rounded text-text-secondary">{m.memory_type}</span>
                <span>importance {m.importance.toFixed(2)}</span>
                <span>confidence {m.confidence.toFixed(2)}</span>
                <span>{m.access_count} reads</span>
                {m.tags?.map((tag) => (
                  <span key={tag} className="text-slate font-display font-semibold">#{tag}</span>
                ))}
              </div>
              <div className="mt-2 text-[10px] font-mono text-text-tertiary truncate">{m.id}</div>
            </div>
          ))}
        </div>
      )}

      {total > limit && (
        <div className="flex items-center justify-between mt-8 max-w-4xl text-sm text-text-secondary font-display font-semibold">
          <button
            disabled={offset === 0}
            onClick={() => setOffset((o) => Math.max(0, o - limit))}
            className="px-4 py-2 rounded-lg bg-surface-1 border border-border-subtle hover:bg-surface-2 text-text-primary disabled:opacity-30 transition-colors"
          >
            Previous
          </button>
          <span>Page {page} of {totalPages}</span>
          <button
            disabled={offset + limit >= total}
            onClick={() => setOffset((o) => o + limit)}
            className="px-4 py-2 rounded-lg bg-surface-1 border border-border-subtle hover:bg-surface-2 text-text-primary disabled:opacity-30 transition-colors"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
