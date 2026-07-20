"use client";

import { useEffect, useState } from "react";
import { Settings01Icon, FloppyDiskIcon, Shield01Icon, CpuIcon, AiLockIcon } from "hugeicons-react";
import { apiFetch } from "@/lib/api";

export default function EngineSettings() {
  const [settings, setSettings] = useState<any>(null);
  const [providers, setProviders] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([
      apiFetch("/api/settings").then((res) => res.json()),
      apiFetch("/api/providers")
        .then((res) => res.json())
        .catch(() => [])
    ])
      .then(([settingsData, providersData]) => {
        setSettings(settingsData);
        setProviders(providersData);
      })
      .catch((err) => console.warn("Backend offline:", err))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await apiFetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      // brief flash to indicate save
      setTimeout(() => setSaving(false), 500);
    } catch (e) {
      console.error(e);
      setSaving(false);
    }
  };

  const updateSecurity = (key: string, val: boolean) => {
    setSettings((prev: any) => ({
      ...prev,
      security: { ...prev.security, [key]: val }
    }));
  };

  const updateRoot = (key: string, val: string) => {
    setSettings((prev: any) => ({ ...prev, [key]: val }));
  };

  const updateTelegram = (key: string, val: boolean) => {
    setSettings((prev: any) => ({
      ...prev,
      telegram: { ...prev.telegram, [key]: val }
    }));
  };

  if (loading || !settings) {
    return <div className="h-full flex items-center justify-center text-terracotta animate-pulse font-display font-semibold">Loading settings...</div>;
  }

  return (
    <div className="h-full bg-canvas text-text-secondary p-8 overflow-y-auto">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-12 border-b border-border-subtle pb-6">
        <div className="flex items-center gap-4 text-text-primary">
          <Settings01Icon className="w-8 h-8 text-terracotta" />
          <div>
            <h2 className="text-2xl font-display font-semibold tracking-wider text-text-primary uppercase">Engine Configuration</h2>
            <p className="text-xs text-text-secondary mt-1 font-serif">Manage core SILEX settings and security policies.</p>
          </div>
        </div>
        <button 
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-5 py-2.5 bg-terracotta text-background hover:opacity-90 rounded-lg font-display font-semibold transition-all disabled:opacity-50"
        >
          <FloppyDiskIcon className="w-5 h-5" />
          {saving ? "Saving..." : "Save Configuration"}
        </button>
      </div>

      <div className="max-w-4xl space-y-16 pb-20">
        
        {/* Model Configuration */}
        <section className="bg-surface-1 border border-border-subtle rounded-xl p-6 card-frame">
          <div className="flex items-center gap-3 text-text-primary font-semibold mb-6">
            <CpuIcon className="w-5 h-5 text-terracotta" />
            <h3 className="text-lg font-display font-semibold tracking-wide text-text-primary">Neural Providers</h3>
          </div>
          
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-display font-bold text-text-tertiary uppercase mb-2">Active Provider</label>
              <select 
                value={settings.provider || "gemini"} 
                onChange={(e) => updateRoot("provider", e.target.value)}
                className="w-full bg-surface-2 border border-border-subtle rounded-lg p-3 text-text-primary focus:outline-none focus:border-terracotta font-serif"
              >
                {(providers.length > 0 ? providers : [
                  { name: "gemini", display_name: "Google Gemini" },
                  { name: "openai", display_name: "OpenAI" },
                  { name: "azure", display_name: "Azure OpenAI" },
                  { name: "anthropic", display_name: "Anthropic" },
                  { name: "ollama", display_name: "Ollama (Local)" },
                  { name: "custom", display_name: "Custom Configuration" }
                ]).map((p) => (
                  <option key={p.name} value={p.name}>
                    {p.display_name}
                  </option>
                ))}
              </select>
            </div>
            
            <div>
              <label className="block text-xs font-display font-bold text-text-tertiary uppercase mb-2">Primary Model</label>
              <input 
                type="text" 
                value={settings.model || ""} 
                onChange={(e) => updateRoot("model", e.target.value)}
                className="w-full bg-surface-2 border border-border-subtle rounded-lg p-3 text-text-primary focus:outline-none focus:border-terracotta font-mono text-sm"
              />
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-display font-bold text-text-tertiary uppercase mb-2">Fast Model (Tools)</label>
                <input 
                  type="text" 
                  value={settings.fast_model || ""} 
                  onChange={(e) => updateRoot("fast_model", e.target.value)}
                  className="w-full bg-surface-2 border border-border-subtle rounded-lg p-3 text-text-primary focus:outline-none focus:border-terracotta font-mono text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-display font-bold text-text-tertiary uppercase mb-2">Reasoning Model (Critique)</label>
                <input 
                  type="text" 
                  value={settings.reasoning_model || ""} 
                  onChange={(e) => updateRoot("reasoning_model", e.target.value)}
                  className="w-full bg-surface-2 border border-border-subtle rounded-lg p-3 text-text-primary focus:outline-none focus:border-terracotta font-mono text-sm"
                />
              </div>
            </div>
          </div>
        </section>

        {/* Security & Autonomy */}
        <section className="bg-surface-1 border border-border-subtle rounded-xl p-6 card-frame">
          <div className="flex items-center gap-3 text-text-primary font-semibold mb-6">
            <Shield01Icon className="w-5 h-5 text-terracotta" />
            <h3 className="text-lg font-display font-semibold tracking-wide text-text-primary">Autonomy & Safety</h3>
          </div>

          <div className="space-y-4 divide-y divide-border-subtle">
            <label className="flex items-center justify-between py-4 cursor-pointer group">
              <div>
                <div className="text-text-primary font-display font-semibold group-hover:text-text-primary transition-colors">Require Tool Approvals</div>
                <div className="text-xs text-text-secondary mt-1 font-serif">Require human confirmation before executing high-risk tools.</div>
              </div>
              <div className="relative inline-flex items-center">
                <input 
                  type="checkbox" 
                  checked={settings.security?.require_tool_approvals ?? true}
                  onChange={(e) => updateSecurity("require_tool_approvals", e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-surface-2 border border-border-subtle peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-text-secondary after:border-border-subtle after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-sage peer-checked:after:bg-text-primary"></div>
              </div>
            </label>

            <label className="flex items-center justify-between py-4 cursor-pointer group">
              <div>
                <div className="text-text-primary font-display font-semibold group-hover:text-text-primary transition-colors">Terminal Execution</div>
                <div className="text-xs text-text-secondary mt-1 font-serif">Allow Kinthic to run arbitrary CLI commands in the workspace.</div>
              </div>
              <div className="relative inline-flex items-center">
                <input 
                  type="checkbox" 
                  checked={settings.security?.terminal_execution ?? false}
                  onChange={(e) => updateSecurity("terminal_execution", e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-surface-2 border border-border-subtle peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-text-secondary after:border-border-subtle after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-sage peer-checked:after:bg-text-primary"></div>
              </div>
            </label>

            <label className="flex items-center justify-between py-4 cursor-pointer group">
              <div>
                <div className="text-text-primary font-display font-semibold group-hover:text-text-primary transition-colors">Code Application</div>
                <div className="text-xs text-text-secondary mt-1 font-serif">Allow direct file modification and code injection without manual patching.</div>
              </div>
              <div className="relative inline-flex items-center">
                <input 
                  type="checkbox" 
                  checked={settings.security?.code_apply ?? false}
                  onChange={(e) => updateSecurity("code_apply", e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-surface-2 border border-border-subtle peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-text-secondary after:border-border-subtle after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-sage peer-checked:after:bg-text-primary"></div>
              </div>
            </label>
            
            <label className="flex items-center justify-between py-4 cursor-pointer group">
              <div>
                <div className="text-text-primary font-display font-semibold group-hover:text-text-primary transition-colors">Background Autonomy</div>
                <div className="text-xs text-text-secondary mt-1 font-serif">Allow Kinthic to proactively wake up and execute asynchronous goals.</div>
              </div>
              <div className="relative inline-flex items-center">
                <input 
                  type="checkbox" 
                  checked={settings.security?.background_actions ?? false}
                  onChange={(e) => updateSecurity("background_actions", e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-surface-2 border border-border-subtle peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-text-secondary after:border-border-subtle after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-sage peer-checked:after:bg-text-primary"></div>
              </div>
            </label>
          </div>
        </section>

        {/* Telegram specific settings */}
        <section className="bg-surface-1 border border-border-subtle rounded-xl p-6 card-frame">
          <div className="flex items-center gap-3 text-text-primary font-semibold mb-6">
            <AiLockIcon className="w-5 h-5 text-terracotta" />
            <h3 className="text-lg font-display font-semibold tracking-wide text-text-primary">Access Control</h3>
          </div>

          <div className="space-y-4">
             <label className="flex items-center justify-between py-2 cursor-pointer group">
              <div>
                <div className="text-text-primary font-display font-semibold group-hover:text-text-primary transition-colors">Telegram Public Mode</div>
                <div className="text-xs text-text-secondary mt-1 font-serif">Allow ANY user on Telegram to interact with this node without a pairing code.</div>
              </div>
              <div className="relative inline-flex items-center">
                <input 
                  type="checkbox" 
                  checked={settings.telegram?.public_mode ?? false}
                  onChange={(e) => updateTelegram("public_mode", e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-surface-2 border border-border-subtle peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-text-secondary after:border-border-subtle after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-sage peer-checked:after:bg-text-primary"></div>
              </div>
            </label>
          </div>
        </section>

      </div>
    </div>
  );
}
