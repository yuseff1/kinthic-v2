"use client";

import { useEffect, useState } from "react";
import { LinkSquare02Icon, Copy01Icon, CheckmarkCircle01Icon, Plug01Icon } from "hugeicons-react";
import { apiFetch } from "@/lib/api";

type McpTool = { name: string; description: string };

type IntegrationsData = {
  mcp_active: boolean;
  http_endpoint: string;
  health_endpoint: string;
  stdio_command: string;
  stdio_command_python: string;
  claude_config: object;
  cursor_config: object;
  tools: McpTool[];
};

export default function IntegrationsPanel() {
  const [data, setData] = useState<IntegrationsData | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [client, setClient] = useState<"claude" | "cursor">("claude");

  useEffect(() => {
    apiFetch("/api/integrations")
      .then((res) => res.json())
      .then(setData)
      .catch((err) => console.warn("Failed to load integrations:", err));
  }, []);

  const copyText = async (key: string, text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(null), 2000);
  };

  const configJson = data
    ? JSON.stringify(client === "cursor" ? data.cursor_config : data.claude_config, null, 2)
    : "";

  if (!data) {
    return (
      <div className="h-full flex items-center justify-center text-terracotta animate-pulse font-display">
        Loading integrations...
      </div>
    );
  }

  return (
    <div className="h-full bg-canvas text-text-secondary p-6 overflow-y-auto">
      <div className="flex items-center gap-3 mb-6 text-text-primary border-b border-border-subtle pb-4">
        <Plug01Icon className="w-7 h-7 text-terracotta" />
        <div>
          <h2 className="text-xl font-display font-semibold tracking-wider text-text-primary uppercase">Integrations</h2>
          <p className="text-xs text-text-secondary mt-1 font-serif">
            Connect Claude Desktop, Cursor, or any MCP client to Silex memory
          </p>
        </div>
      </div>

      <div className="max-w-3xl space-y-8">
        <section className="bg-surface-1 border border-border-subtle rounded-xl p-5 card-frame">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xs font-display font-semibold tracking-wider text-text-tertiary uppercase">Status</h3>
            <span
              className={`text-xs font-display font-semibold px-2.5 py-1 rounded ${
                data.mcp_active ? "bg-sage/10 text-sage" : "bg-terracotta/10 text-terracotta"
              }`}
            >
              {data.mcp_active ? "MCP ACTIVE" : "MCP OFFLINE"}
            </span>
          </div>
          <div className="space-y-3 text-sm">
            <CopyRow
              label="HTTP endpoint"
              value={data.http_endpoint}
              copied={copied === "http"}
              onCopy={() => copyText("http", data.http_endpoint)}
            />
            <CopyRow
              label="stdio bridge"
              value={data.stdio_command}
              copied={copied === "stdio"}
              onCopy={() => copyText("stdio", data.stdio_command)}
            />
            <CopyRow
              label="stdio (Python fallback)"
              value={data.stdio_command_python}
              copied={copied === "stdio_py"}
              onCopy={() => copyText("stdio_py", data.stdio_command_python)}
            />
          </div>
        </section>

        <section className="bg-surface-1 border border-border-subtle rounded-xl p-5 card-frame">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xs font-display font-semibold tracking-wider text-text-tertiary uppercase">Client Config</h3>
            <div className="flex gap-1 bg-surface-2 rounded-lg p-1 border border-border-subtle">
              {(["claude", "cursor"] as const).map((c) => (
                <button
                  key={c}
                  onClick={() => setClient(c)}
                  className={`px-3 py-1 text-xs rounded capitalize font-display ${
                    client === c ? "bg-surface-1 border border-border-strong text-terracotta" : "text-text-tertiary hover:text-text-secondary border border-transparent"
                  }`}
                >
                  {c}
                </button>
              ))}
            </div>
          </div>
          <pre className="bg-surface-2 border border-border-subtle rounded-lg p-4 text-xs font-mono text-text-primary overflow-x-auto">
            {configJson}
          </pre>
          <button
            onClick={() => copyText("config", configJson)}
            className="mt-3 flex items-center gap-2 px-4 py-2 bg-surface-2 hover:bg-surface-1 border border-border-subtle rounded-lg text-sm font-display font-semibold text-text-primary transition-colors"
          >
            {copied === "config" ? (
              <CheckmarkCircle01Icon className="w-4 h-4 text-sage" />
            ) : (
              <Copy01Icon className="w-4 h-4" />
            )}
            Copy JSON
          </button>
          <p className="mt-3 text-xs text-text-tertiary font-serif">
            Paste into your MCP client config. Requires kinthic web or daemon running for the stdio bridge to proxy to the gateway.
          </p>
        </section>

        <section className="bg-surface-1 border border-border-subtle rounded-xl p-5 card-frame">
          <h3 className="text-xs font-display font-semibold tracking-wider text-text-tertiary uppercase mb-4">
            Silex MCP Tools ({data.tools.length})
          </h3>
          <div className="space-y-3">
            {data.tools.map((tool) => (
              <div key={tool.name} className="border-b border-border-subtle pb-3 last:border-0">
                <div className="font-mono text-sm text-slate font-semibold">{tool.name}</div>
                <div className="text-xs text-text-secondary mt-1 font-serif">{tool.description}</div>
              </div>
            ))}
          </div>
        </section>

        <a
          href={data.http_endpoint}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-2 text-sm text-text-secondary hover:text-text-primary font-display font-semibold transition-colors"
        >
          <LinkSquare02Icon className="w-4 h-4" />
          Open MCP endpoint
        </a>
      </div>
    </div>
  );
}

function CopyRow({
  label,
  value,
  copied,
  onCopy,
}: {
  label: string;
  value: string;
  copied: boolean;
  onCopy: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="min-w-0">
        <div className="text-xs text-text-tertiary uppercase mb-0.5 font-display">{label}</div>
        <div className="font-mono text-text-primary truncate">{value}</div>
      </div>
      <button
        onClick={onCopy}
        className="shrink-0 p-2 rounded-lg bg-surface-2 border border-border-subtle hover:bg-surface-1 text-text-secondary hover:text-text-primary transition-colors"
        title="Copy"
      >
        {copied ? (
          <CheckmarkCircle01Icon className="w-4 h-4 text-sage" />
        ) : (
          <Copy01Icon className="w-4 h-4" />
        )}
      </button>
    </div>
  );
}
