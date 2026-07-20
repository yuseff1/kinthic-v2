"use client";

import { useCallback, useEffect, useState } from "react";
import {
  BookOpen01Icon,
  Search01Icon,
  RefreshIcon,
  Download01Icon,
  Delete02Icon,
  Cancel01Icon,
} from "hugeicons-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { apiFetch } from "@/lib/api";

type Skill = {
  name: string;
  description: string;
  trust_level: string;
  trigger?: string;
  source?: string;
  layout?: string;
  size_bytes?: number;
};

type CatalogEntry = {
  name: string;
  description: string;
  trust_level?: string;
  installed?: boolean;
  tags?: string[];
};

const TRUST_COLORS: Record<string, string> = {
  core: "text-sage bg-sage/10 border-sage/20",
  verified: "text-slate bg-slate/10 border-slate/20",
  community: "text-text-secondary bg-surface-1 border-border-subtle",
};

export default function SkillForge() {
  const [tab, setTab] = useState<"installed" | "catalog">("installed");
  const [skills, setSkills] = useState<Skill[]>([]);
  const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [statusIsError, setStatusIsError] = useState(false);
  const [urlInstall, setUrlInstall] = useState("");

  const [detail, setDetail] = useState<{
    name: string;
    body: string;
    metadata: Record<string, any>;
  } | null>(null);

  const loadInstalled = useCallback(async () => {
    try {
      const res = await apiFetch("/api/skills");
      if (!res.ok) throw new Error("Failed to load skills");
      const json = await res.json();
      setSkills(json.skills || []);
    } catch (err: any) {
      console.error(err);
      setLoadError(err.message || "Failed to load installed skills");
    }
  }, []);

  const loadCatalog = useCallback(async (q?: string) => {
    try {
      const path = q ? `/api/skills/catalog?q=${encodeURIComponent(q)}` : "/api/skills/catalog";
      const res = await apiFetch(path);
      if (!res.ok) throw new Error("Failed to load catalog");
      const json = await res.json();
      setCatalog(json.entries || []);
    } catch (err: any) {
      console.error(err);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    Promise.all([loadInstalled(), loadCatalog()]).finally(() => setLoading(false));
  }, [loadInstalled, loadCatalog]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    loadCatalog(query).finally(() => setLoading(false));
  };

  const handleRefreshHub = async () => {
    setBusy("refresh");
    setStatus("Refreshing community skills hub...");
    setStatusIsError(false);
    try {
      const res = await apiFetch("/api/skills/sync", { method: "POST" });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Sync failed");
      setStatus(`Hub updated: ${json.summary || "Success"}`);
      await Promise.all([loadInstalled(), loadCatalog(query)]);
    } catch (err: any) {
      setStatus(`Sync error: ${err.message}`);
      setStatusIsError(true);
    } finally {
      setBusy(null);
    }
  };

  const handleInstall = async (name: string) => {
    setBusy(name);
    setStatus(`Installing skill: ${name}...`);
    setStatusIsError(false);
    try {
      const res = await apiFetch("/api/skills/install", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Install failed");
      setStatus(`Successfully installed ${name}`);
      await Promise.all([loadInstalled(), loadCatalog(query)]);
    } catch (err: any) {
      setStatus(`Install error: ${err.message}`);
      setStatusIsError(true);
    } finally {
      setBusy(null);
    }
  };

  const handleUrlInstall = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!urlInstall.trim()) return;
    setBusy("url");
    setStatus("Installing skill from URL...");
    setStatusIsError(false);
    try {
      const res = await apiFetch("/api/skills/install_url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: urlInstall.trim() }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Install failed");
      setStatus(`Successfully installed skill: ${json.name}`);
      setUrlInstall("");
      await Promise.all([loadInstalled(), loadCatalog(query)]);
    } catch (err: any) {
      setStatus(`URL Install error: ${err.message}`);
      setStatusIsError(true);
    } finally {
      setBusy(null);
    }
  };

  const handleUninstall = async (name: string) => {
    if (!confirm(`Are you sure you want to uninstall the skill "${name}"?`)) return;
    setBusy(name);
    setStatus(`Uninstalling skill: ${name}...`);
    setStatusIsError(false);
    try {
      const res = await apiFetch("/api/skills/uninstall", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Uninstall failed");
      setStatus(`Successfully uninstalled ${name}`);
      if (detail?.name === name) setDetail(null);
      await Promise.all([loadInstalled(), loadCatalog(query)]);
    } catch (err: any) {
      setStatus(`Uninstall error: ${err.message}`);
      setStatusIsError(true);
    } finally {
      setBusy(null);
    }
  };

  const openDetail = async (name: string) => {
    try {
      const res = await apiFetch(`/api/skills/view?name=${encodeURIComponent(name)}`);
      if (!res.ok) throw new Error("Could not retrieve skill instructions");
      const json = await res.json();
      setDetail({
        name,
        body: json.body || "",
        metadata: json.metadata || {},
      });
    } catch (err: any) {
      alert(err.message || "Failed to load skill details");
    }
  };

  const openCatalogPreview = async (entry: CatalogEntry) => {
    try {
      const res = await apiFetch(`/api/skills/view?name=${encodeURIComponent(entry.name)}&catalog=true`);
      if (!res.ok) throw new Error("Could not preview skill instructions");
      const json = await res.json();
      setDetail({
        name: entry.name,
        body: json.body || "",
        metadata: entry,
      });
    } catch (err: any) {
      alert(err.message || "Failed to load catalog preview");
    }
  };

  const trustBadge = (level: string) => {
    const colorClass = TRUST_COLORS[level] || TRUST_COLORS.community;
    return (
      <span className={`text-[10px] px-2 py-0.5 rounded-full border uppercase font-bold tracking-wider font-display ${colorClass}`}>
        {level}
      </span>
    );
  };

  return (
    <div className="h-full bg-canvas text-text-secondary flex flex-col overflow-hidden">
      <div className="p-6 border-b border-border-subtle shrink-0">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <BookOpen01Icon className="w-7 h-7 text-terracotta" />
            <div>
              <h2 className="text-xl font-display font-semibold tracking-wider text-text-primary uppercase">Skill Forge</h2>
              <p className="text-xs text-text-secondary mt-1 font-serif">
                Workflow skills — bundled, synthesized, and community packs
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => {
                setLoadError(null);
                Promise.all([loadInstalled(), loadCatalog(query)]).catch((err) =>
                  setLoadError(err.message || "Reload failed")
                );
              }}
              className="p-2.5 rounded-lg bg-surface-1 border border-border-subtle hover:border-border-strong text-text-secondary hover:text-text-primary transition-colors"
              title="Reload"
            >
              <RefreshIcon className="w-5 h-5" />
            </button>
            <button
              onClick={handleRefreshHub}
              disabled={busy === "refresh"}
              className="px-4 py-2 rounded-lg bg-surface-1 hover:bg-surface-2 border border-border-subtle text-sm font-display font-semibold text-text-primary disabled:opacity-50 transition-colors"
            >
              Refresh Hub
            </button>
          </div>
        </div>

        {loadError && (
          <div className="mt-4 p-3 rounded-lg bg-terracotta/10 border border-terracotta/30 text-sm text-terracotta font-serif">
            {loadError}
          </div>
        )}

        {status && (
          <div
            className={`mt-4 p-3 rounded-lg text-sm border font-serif ${
              statusIsError
                ? "bg-terracotta/10 border-terracotta/30 text-terracotta"
                : "bg-sage/10 border-sage/20 text-sage"
            }`}
          >
            {status}
          </div>
        )}

        <div className="flex gap-4 mt-4 items-center flex-wrap">
          <div className="flex gap-1 bg-surface-2 rounded-lg p-1 border border-border-subtle">
            {(["installed", "catalog"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-4 py-1.5 text-sm rounded capitalize font-display ${
                  tab === t ? "bg-surface-1 border border-border-strong text-terracotta" : "text-text-tertiary hover:text-text-secondary border border-transparent"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
          <form onSubmit={handleSearch} className="flex gap-2 flex-1 min-w-[200px] max-w-md">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search catalog..."
              className="flex-1 bg-surface-1 border border-border-subtle rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-terracotta transition-colors"
            />
            <button type="submit" className="p-2 rounded-lg bg-surface-1 border border-border-subtle text-text-secondary hover:text-text-primary transition-colors">
              <Search01Icon className="w-4 h-4" />
            </button>
          </form>
          <form onSubmit={handleUrlInstall} className="flex gap-2 flex-1 min-w-[240px] max-w-lg">
            <input
              value={urlInstall}
              onChange={(e) => setUrlInstall(e.target.value)}
              placeholder="Install from https://…/skill.md"
              className="flex-1 bg-surface-1 border border-border-subtle rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-terracotta transition-colors"
            />
            <button
              type="submit"
              disabled={busy === "url"}
              className="px-3 py-2 rounded-lg bg-terracotta/10 hover:bg-terracotta/20 text-xs font-display font-semibold text-terracotta border border-terracotta/20 disabled:opacity-50 transition-colors"
            >
              URL Install
            </button>
          </form>
        </div>
      </div>

      <div className="flex-1 overflow-hidden flex">
        <div className={`flex-1 overflow-y-auto p-6 ${detail ? "hidden lg:block lg:w-1/2" : "w-full"}`}>
          {loading ? (
            <div className="text-terracotta animate-pulse font-display">Loading skills...</div>
          ) : tab === "installed" ? (
            skills.length === 0 ? (
              <div className="p-8 border border-dashed border-border-subtle rounded-xl text-center text-text-tertiary font-serif">
                No skills loaded. Install from the catalog or let Genesis synthesize from successful trajectories.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {skills.map((skill) => (
                  <SkillCard
                     key={skill.name}
                     skill={skill}
                     busy={busy === skill.name}
                     onView={() => openDetail(skill.name)}
                     onUninstall={() => handleUninstall(skill.name)}
                     trustBadge={trustBadge}
                  />
                ))}
              </div>
            )
          ) : catalog.length === 0 ? (
            <div className="p-8 border border-dashed border-border-subtle rounded-xl text-center text-text-tertiary font-serif">
              No catalog entries match. Try Refresh Hub to pull remote skills.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {catalog.map((entry) => (
                <div
                  key={entry.name}
                  className="bg-surface-1 border border-border-subtle rounded-xl p-4 hover:border-border-strong transition-all duration-300 card-frame"
                >
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <h3 className="font-display font-semibold text-text-primary truncate">{entry.name}</h3>
                    {trustBadge(entry.trust_level || "community")}
                  </div>
                  <p className="text-xs text-text-secondary line-clamp-3 mb-3 font-serif">{entry.description}</p>
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => openCatalogPreview(entry)}
                      className="text-xs text-text-primary bg-surface-2 border border-border-subtle px-3 py-1 rounded-lg hover:bg-surface-1 transition-colors font-display"
                    >
                      Preview
                    </button>
                    {entry.installed ? (
                      <span className="text-xs text-sage font-display">Installed</span>
                    ) : (
                      <button
                        onClick={() => handleInstall(entry.name)}
                        disabled={busy === entry.name}
                        className="flex items-center gap-1 text-xs font-display font-semibold text-terracotta hover:text-terracotta/90 disabled:opacity-50 transition-colors"
                      >
                        <Download01Icon className="w-3.5 h-3.5" />
                        Install
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {detail && (
          <div className="w-full lg:w-1/2 border-l border-border-subtle flex flex-col bg-surface-2">
            <div className="p-4 border-b border-border-subtle flex items-center justify-between shrink-0">
              <div>
                <h3 className="font-display font-semibold text-text-primary">{detail.name}</h3>
                <div className="flex gap-2 mt-1">
                  {detail.metadata.trust_level && trustBadge(detail.metadata.trust_level)}
                  {detail.metadata.source && (
                    <span className="text-[10px] text-text-tertiary uppercase font-display">{detail.metadata.source}</span>
                  )}
                </div>
              </div>
              <button onClick={() => setDetail(null)} className="p-2 text-text-secondary hover:text-text-primary transition-colors">
                <Cancel01Icon className="w-5 h-5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-6 prose prose-invert prose-sm max-w-none font-serif">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{detail.body}</ReactMarkdown>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function SkillCard({
  skill,
  busy,
  onView,
  onUninstall,
  trustBadge,
}: {
  skill: Skill;
  busy: boolean;
  onView: () => void;
  onUninstall: () => void;
  trustBadge: (level: string) => React.ReactNode;
}) {
  return (
    <div className="bg-surface-1 border border-border-subtle rounded-xl p-4 hover:border-border-strong transition-all duration-300 card-frame group">
      <div className="flex items-start justify-between gap-2 mb-2">
        <button onClick={onView} className="font-display font-semibold text-text-primary truncate text-left hover:text-terracotta transition-colors">
          {skill.name}
        </button>
        {trustBadge(skill.trust_level || "community")}
      </div>
      <p className="text-xs text-text-secondary line-clamp-2 mb-2 font-serif">{skill.description}</p>
      <div className="flex flex-wrap gap-2 text-[10px] text-text-tertiary uppercase font-display">
        {skill.source && <span>{skill.source}</span>}
        {skill.layout && <span>{skill.layout}</span>}
        {skill.trigger && <span className="normal-case text-text-tertiary font-serif">trigger: {skill.trigger}</span>}
      </div>
      <div className="flex gap-2 mt-3 opacity-0 group-hover:opacity-100 transition-opacity">
        <button onClick={onView} className="text-xs text-text-primary bg-surface-2 border border-border-subtle px-3 py-1 rounded-lg hover:bg-surface-1 transition-colors font-display">
          View
        </button>
        <button
          onClick={onUninstall}
          disabled={busy}
          className="text-xs text-terracotta hover:text-terracotta/90 disabled:opacity-50 flex items-center gap-1 font-display transition-colors"
        >
          <Delete02Icon className="w-3.5 h-3.5" />
          Remove
        </button>
      </div>
    </div>
  );
}
