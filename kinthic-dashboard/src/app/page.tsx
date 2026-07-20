"use client";

import EpistemicGraph from '@/components/EpistemicGraph';
import TerminalOutput from '@/components/TerminalOutput';
import SkillForge from '@/components/SkillForge';
import SystemMetrics from '@/components/SystemMetrics';
import EngineSettings from '@/components/EngineSettings';
import MemoryBrowser from '@/components/MemoryBrowser';
import DataVault from '@/components/DataVault';
import IntegrationsPanel from '@/components/IntegrationsPanel';
import {
  ComputerTerminal01Icon,
  NeuralNetworkIcon,
  Settings01Icon,
  BookOpen01Icon,
  Activity01Icon,
  Database01Icon,
  FloppyDiskIcon,
  Plug01Icon,
} from 'hugeicons-react';
import { useState } from 'react';

type Tab =
  | 'graph'
  | 'terminal'
  | 'skills'
  | 'memories'
  | 'data'
  | 'integrations'
  | 'metrics'
  | 'settings';

export default function Home() {
  const [activeTab, setActiveTab] = useState<Tab>('graph');

  const navBtn = (tab: Tab, label: string, Icon: typeof NeuralNetworkIcon) => (
    <button
      onClick={() => setActiveTab(tab)}
      className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors font-medium border ${
        activeTab === tab 
          ? 'bg-surface-1 border-border-strong text-terracotta' 
          : 'text-text-secondary hover:bg-surface-1 hover:text-text-primary border-transparent'
      }`}
    >
      <Icon className={`w-5 h-5 ${activeTab === tab ? 'text-terracotta' : 'text-text-secondary'}`} />
      {label}
    </button>
  );

  return (
    <main className="flex h-screen w-screen relative">
      <aside className="w-[320px] shrink-0 border-r border-border-subtle bg-surface-2 flex flex-col z-20">
        <div className="p-6 border-b border-border-subtle flex items-center justify-between">
          <div>
            <h1 className="text-xl font-display font-bold tracking-wider text-text-primary">
              KINTHIC
            </h1>
            <div className="mt-2 flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sage opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-sage"></span>
              </span>
              <span className="text-xs font-display font-semibold tracking-wider text-text-secondary uppercase">
                Studio Online
              </span>
            </div>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto p-4 space-y-2">
          <div className="text-xs font-display font-bold text-text-tertiary uppercase tracking-widest mb-4 mt-2 px-2">Core</div>
          {navBtn('graph', 'Epistemic Topology', NeuralNetworkIcon)}
          {navBtn('terminal', 'Terminal Output', ComputerTerminal01Icon)}
          {navBtn('skills', 'Skill Forge', BookOpen01Icon)}
          {navBtn('memories', 'Memory Browser', Database01Icon)}

          <div className="text-xs font-display font-bold text-text-tertiary uppercase tracking-widest mb-4 mt-6 px-2">System</div>
          {navBtn('data', 'Data Vault', FloppyDiskIcon)}
          {navBtn('integrations', 'Integrations', Plug01Icon)}
          {navBtn('metrics', 'System Metrics', Activity01Icon)}
        </nav>

        <div className="p-4 border-t border-border-subtle">
          <button
            onClick={() => setActiveTab('settings')}
            className={`w-full flex items-center justify-center gap-2 px-4 py-2 rounded-md text-sm font-semibold transition-colors border ${
              activeTab === 'settings' 
                ? 'bg-surface-1 border-border-strong text-terracotta' 
                : 'text-text-secondary hover:text-text-primary hover:bg-surface-1 border-transparent'
            }`}
          >
            <Settings01Icon className="w-4 h-4" />
            Engine Settings
          </button>
        </div>
      </aside>

      <section className="flex-1 relative bg-canvas overflow-hidden">
        <div className="absolute inset-0">
          <div className={activeTab === 'graph' ? 'w-full h-full' : 'hidden'}><EpistemicGraph /></div>
          <div className={activeTab === 'terminal' ? 'w-full h-full' : 'hidden'}><TerminalOutput /></div>
          <div className={activeTab === 'skills' ? 'w-full h-full' : 'hidden'}><SkillForge /></div>
          <div className={activeTab === 'memories' ? 'w-full h-full' : 'hidden'}><MemoryBrowser /></div>
          <div className={activeTab === 'data' ? 'w-full h-full' : 'hidden'}><DataVault /></div>
          <div className={activeTab === 'integrations' ? 'w-full h-full' : 'hidden'}><IntegrationsPanel /></div>
          <div className={activeTab === 'metrics' ? 'w-full h-full' : 'hidden'}><SystemMetrics /></div>
          <div className={activeTab === 'settings' ? 'w-full h-full' : 'hidden'}><EngineSettings /></div>
        </div>

        {activeTab === 'graph' && (
          <div className="absolute top-6 left-1/2 -translate-x-1/2 z-10 pointer-events-none">
            <div className="bg-surface-1/90 backdrop-blur-md border border-border-strong rounded-full px-5 py-2 flex items-center gap-3">
              <NeuralNetworkIcon className="w-4 h-4 text-terracotta" />
              <h2 className="text-sm font-display font-semibold text-text-primary tracking-wide whitespace-nowrap">
                World Model State
              </h2>
              <div className="w-1 h-1 rounded-full bg-border-strong"></div>
              <p className="text-xs text-text-secondary whitespace-nowrap">Live rendering</p>
            </div>
          </div>
        )}
      </section>
    </main>
  );
}
