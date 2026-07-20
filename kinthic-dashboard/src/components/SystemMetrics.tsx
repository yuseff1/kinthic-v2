"use client";

import { useEffect, useState } from "react";
import { Activity01Icon, Database01Icon, NeuralNetworkIcon, AiBrain01Icon, BinaryCodeIcon } from "hugeicons-react";
import { apiFetch } from "@/lib/api";

export default function SystemMetrics() {
  const [metrics, setMetrics] = useState<any>(null);

  useEffect(() => {
    apiFetch("/api/metrics")
      .then((res) => res.json())
      .then((data) => setMetrics(data))
      .catch((err) => console.warn("Backend offline:", err));
      
    const int = setInterval(() => {
      apiFetch("/api/metrics")
        .then((res) => res.json())
        .then((data) => setMetrics(data))
        .catch((err) => console.warn("Backend offline:", err));
    }, 5000);
    return () => clearInterval(int);
  }, []);

  const stats = [
    { label: "Epistemic Nodes", value: metrics?.nodes || 0, icon: NeuralNetworkIcon, color: "text-terracotta" },
    { label: "Relational Edges", value: metrics?.edges || 0, icon: Activity01Icon, color: "text-slate" },
    { label: "Archived Memories", value: metrics?.memories || 0, icon: Database01Icon, color: "text-sage" },
    { label: "Synthesized Trajectories", value: metrics?.trajectories || 0, icon: AiBrain01Icon, color: "text-slate" },
  ];

  return (
    <div className="h-full bg-canvas text-text-secondary p-8 flex flex-col justify-center items-center">
      <div className="w-full max-w-4xl">
        <h2 className="text-3xl font-display font-bold tracking-wider text-text-primary mb-2 uppercase text-center">
          Core Telemetry
        </h2>
        <p className="text-center text-text-tertiary mb-12 font-display uppercase tracking-widest text-xs">Real-time subsystem analytics</p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {stats.map((stat, i) => (
            <div key={i} className="bg-surface-1 border border-border-subtle rounded-xl p-6 flex items-center gap-6 card-frame">
              <div className={`p-4 rounded-lg bg-surface-2 border border-border-subtle ${stat.color}`}>
                <stat.icon className="w-8 h-8" />
              </div>
              <div>
                <div className="text-xs font-display font-bold tracking-wider text-text-tertiary uppercase mb-1">{stat.label}</div>
                <div className="text-4xl font-mono font-bold text-text-primary">
                  {metrics === null ? "..." : stat.value.toLocaleString()}
                </div>
              </div>
            </div>
          ))}
        </div>
        
        <div className="mt-12 p-6 bg-surface-1 border border-border-subtle rounded-xl flex items-center gap-4 text-text-secondary">
          <BinaryCodeIcon className="w-5 h-5 text-terracotta" />
          <div className="text-sm space-y-1 font-serif">
            <div>
              Gateway Server: <span className="text-sage font-mono font-bold">ONLINE</span> (Port 8000)
            </div>
            <div>
              Browser Automation:{" "}
              {metrics?.browser_active ? (
                <span className="text-sage font-mono font-bold">ONLINE</span>
              ) : (
                <span className="text-terracotta font-mono font-bold">OFFLINE</span>
              )}
            </div>
            {metrics?.mcp_server && (
              <div>
                Silex MCP: <span className="text-slate font-mono font-bold">ACTIVE</span> ({metrics?.mcp_tools || 9} tools @ {metrics?.mcp_endpoint || "/mcp"})
              </div>
            )}
            {metrics?.daemon_running && (
              <div>
                Daemon: <span className="text-terracotta font-mono font-bold">RUNNING</span> (stop before restore)
              </div>
            )}
          </div>
        </div>

        {metrics && !metrics.browser_active && (
          <div className="mt-6 w-full max-w-4xl p-6 bg-surface-1 border border-border-strong rounded-xl text-text-secondary flex flex-col gap-3">
            <div className="text-xs font-display font-bold tracking-wider text-text-primary uppercase">
              🌐 Web Browsing Setup Required
            </div>
            <p className="text-xs leading-relaxed text-text-secondary">
              Browser automation capabilities are currently offline. To enable web scraping and visual site inspection, run this command in your active terminal:
            </p>
            <div className="p-3 bg-surface-2 border border-border-subtle rounded font-mono text-xs text-accent-slate select-all cursor-pointer hover:border-border-strong transition-colors">
              pip install -e ".[browser]" && playwright install chromium
            </div>
          </div>
        )}

        {metrics && (metrics.vector_drift > 0 || metrics.writer_dead) && (
          <div className="mt-4 p-6 bg-terracotta/5 border border-terracotta/30 rounded-xl flex items-center gap-4 text-terracotta font-serif">
            <BinaryCodeIcon className="w-5 h-5" />
            <div className="text-sm space-y-1">
              {metrics.writer_dead && <div>⚠️ Database writer loop is dead — restart Kinthic.</div>}
              {metrics.vector_drift > 0 && (
                <div>⚠️ {metrics.vector_drift} memory/vector record(s) out of sync — will self-heal on next restart or reconciliation pass.</div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
