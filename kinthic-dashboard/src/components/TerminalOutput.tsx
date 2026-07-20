"use client";

import { useState, useRef, useEffect } from "react";
import { SentIcon, ComputerTerminal01Icon, StopIcon, CheckmarkCircle01Icon, Cancel01Icon, Attachment01Icon, NeuralNetworkIcon } from "hugeicons-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { atomDark } from "react-syntax-highlighter/dist/cjs/styles/prism";
import TextareaAutosize from "react-textarea-autosize";
import { apiFetch } from "@/lib/api";

type TurnAttachment = {
  name: string;
  url: string;
  type: string;
};

type Turn = {
  id: string;
  role: "user" | "kinthic";
  content: string;
  attachments?: TurnAttachment[];
  thinking?: string;
  processSteps?: { id: string; type: string; content: string; timestamp: number }[];
  toolCalls?: { id: string; name: string; args: any; result?: string }[];
  approval?: { approval_id: string; tool_name: string; risk_level: string; reason: string; arguments_preview: any; resolved?: boolean; approved?: boolean };
  cost?: { total_cost_usd: number; total_tokens: number; turns: number; model: string };
  error?: string;
  cancelled?: boolean;
};

export default function TerminalOutput() {
  const [history, setHistory] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [currentRequestId, setCurrentRequestId] = useState<string | null>(null);
  
  // Command History
  const [commandHistory, setCommandHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);

  // Attachments
  const [attachments, setAttachments] = useState<{file: File, url: string, base64?: string}[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const chatContainerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll logic
  useEffect(() => {
    if (chatContainerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = chatContainerRef.current;
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 150;
      if (isNearBottom) {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
      }
    }
  }, [history]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    files.forEach(file => {
      const reader = new FileReader();
      reader.onload = (ev) => {
        setAttachments(prev => [...prev, {
          file,
          url: URL.createObjectURL(file),
          base64: ev.target?.result as string
        }]);
      };
      reader.readAsDataURL(file);
    });
    if (e.target) e.target.value = '';
  };

  const handleEvent = (turnId: string, event: any) => {
    setHistory(prev => prev.map(turn => {
      if (turn.id !== "kinthic-" + turnId) return turn;
      
      const updated = { ...turn };
      
      switch (event.type) {
        case "thinking":
        case "routing":
        case "context":
          const text = event.data?.status || event.data?.detail || event.type;
          updated.thinking = text;
          updated.processSteps = [...(updated.processSteps || []), {
            id: Date.now().toString() + Math.random().toString(),
            type: event.type,
            content: text,
            timestamp: Date.now()
          }];
          break;
        case "tool_call":
          updated.toolCalls = [...(updated.toolCalls || []), {
            id: event.data?.tool_call_id || Date.now().toString(),
            name: event.data?.name,
            args: event.data?.arguments
          }];
          updated.thinking = `Running tool: ${event.data?.name}...`;
          break;
        case "tool_result":
          // Update the last tool call that doesn't have a result
          if (updated.toolCalls && updated.toolCalls.length > 0) {
              const reversed = [...updated.toolCalls].reverse();
              const target = reversed.find(tc => !tc.result);
              if (target) {
                  target.result = event.data?.result || "Success";
                  updated.toolCalls = reversed.reverse();
              }
          }
          updated.thinking = undefined;
          break;
        case "response":
          updated.content += (event.data?.text || "");
          updated.thinking = undefined;
          break;
        case "approval_requested":
          updated.approval = event.data;
          updated.thinking = "Awaiting user approval...";
          break;
        case "approval_resolved":
          if (updated.approval && updated.approval.approval_id === event.data?.approval_id) {
            updated.approval.resolved = true;
            updated.approval.approved = event.data?.approved;
          }
          updated.thinking = undefined;
          break;
        case "cost_update":
          updated.cost = event.data;
          break;
        case "error":
          updated.error = event.data?.message;
          updated.thinking = undefined;
          break;
        case "cancel":
          updated.cancelled = true;
          updated.thinking = undefined;
          break;
        case "done":
          updated.thinking = undefined;
          break;
      }
      return updated;
    }));
  };

  const handleSend = async () => {
    const cmd = input.trim();
    if ((!cmd && attachments.length === 0) || loading) return;

    // Slash commands
    if (cmd === "/clear") {
      setHistory([]);
      setInput("");
      return;
    }
    
    if (cmd === "/pause" && currentRequestId) {
      handlePause();
      setInput("");
      return;
    }

    if (cmd) {
      setCommandHistory(prev => [...prev, cmd]);
    }
    setHistoryIndex(-1);
    setInput("");

    // Force scroll to bottom on user send
    setTimeout(() => {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, 50);

    const turnId = Date.now().toString();
    setHistory(prev => [
      ...prev, 
      { 
        id: "user-" + turnId, 
        role: "user", 
        content: cmd,
        attachments: attachments.map(a => ({
          name: a.file.name,
          url: a.url,
          type: a.file.type
        }))
      },
      { id: "kinthic-" + turnId, role: "kinthic", content: "", toolCalls: [] }
    ]);
    
    setLoading(true);

    const imagesPayload = attachments.map(a => ({
      data: a.base64?.split(",")[1] || "",
      mime_type: a.file.type,
      name: a.file.name
    }));
    setAttachments([]);

    try {
      const res = await apiFetch("/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: cmd, images: imagesPayload.length > 0 ? imagesPayload : undefined }),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.error || errorData.detail || `HTTP Error ${res.status}`);
      }

      const reqId = res.headers.get("X-Request-Id");
      if (reqId) setCurrentRequestId(reqId);

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();

      if (reader) {
        let done = false;
        let buffer = "";
        while (!done) {
          const { value, done: doneReading } = await reader.read();
          done = doneReading;
          if (value) {
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() || "";

            for (const line of lines) {
              if (!line.trim()) continue;
              try {
                const event = JSON.parse(line);
                handleEvent(turnId, event);
              } catch (e) {
                console.error("Failed to parse event line:", line);
              }
            }
          }
        }
      }
    } catch (err) {
      setHistory(prev => prev.map(t => t.id === "kinthic-" + turnId ? { ...t, error: `Connection Error: ${err}` } : t));
    } finally {
      setLoading(false);
      setCurrentRequestId(null);
    }
  };

  const handlePause = async () => {
    if (currentRequestId) {
      await apiFetch("/api/chat/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_id: currentRequestId }),
      });
    }
  };

  const handleApprove = async (approvalId: string, approved: boolean) => {
    await apiFetch("/api/chat/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approval_id: approvalId, approved }),
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (commandHistory.length > 0 && historyIndex < commandHistory.length - 1) {
        const nextIdx = historyIndex + 1;
        setHistoryIndex(nextIdx);
        setInput(commandHistory[commandHistory.length - 1 - nextIdx]);
      }
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      if (historyIndex > 0) {
        const prevIdx = historyIndex - 1;
        setHistoryIndex(prevIdx);
        setInput(commandHistory[commandHistory.length - 1 - prevIdx]);
      } else if (historyIndex === 0) {
        setHistoryIndex(-1);
        setInput("");
      }
    }
  };

  return (
    <div className="flex flex-col h-full bg-surface-2/40 text-text-secondary font-display text-sm p-4">
      <div className="flex items-center justify-between mb-4 border-b border-border-subtle pb-2">
        <div className="flex items-center gap-3 text-terracotta">
          <ComputerTerminal01Icon className="w-6 h-6" />
          <h2 className="font-display font-bold tracking-wider text-text-primary uppercase">Direct Neural Interface</h2>
        </div>
        
        {loading && (
          <button 
            onClick={handlePause}
            className="flex items-center gap-1 text-xs text-terracotta hover:text-terracotta/90 transition-colors bg-terracotta/10 border border-terracotta/20 px-2.5 py-1 rounded font-display font-semibold"
          >
            <StopIcon className="w-3 h-3" /> Pause Engine
          </button>
        )}
      </div>

      <div ref={chatContainerRef} className="flex-1 overflow-y-auto space-y-4 mb-4 pr-2 custom-scrollbar">
        {history.length === 0 ? (
          <div className="text-text-tertiary italic">Kinthic terminal online. Type /help for commands. Awaiting input...</div>
        ) : (
          history.map((msg) => (
            <div key={msg.id} className={`flex flex-col w-full py-2 ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
              <div
                className={`w-full ${
                  msg.role === "user"
                    ? "max-w-[80%] bg-surface-1 border border-border-strong rounded-lg p-4 text-text-primary shadow-sm"
                    : "max-w-[90%] bg-surface-1/40 border-l-2 border-terracotta border-y border-r border-border-strong/50 rounded-r-lg p-4 text-text-primary shadow-sm"
                }`}
              >
                <div className="flex justify-between items-center mb-2">
                  <div className="text-xs font-display font-bold tracking-wider opacity-60 text-terracotta">
                    {msg.role === "user" ? "USER" : "KINTHIC"}
                  </div>
                  {msg.cost && (
                    <div className="text-[10px] text-text-tertiary font-display">
                      ${msg.cost.total_cost_usd?.toFixed(4)} • {msg.cost.total_tokens} tkns • {msg.cost.model}
                    </div>
                  )}
                </div>

                {/* Tool Calls */}
                {msg.toolCalls?.map((tc, idx) => (
                  <div key={idx} className="mb-3 bg-surface-1 border border-border-subtle rounded-lg p-2 text-xs">
                    <div className="text-slate mb-1 font-semibold font-mono">λ {tc.name}</div>
                    <div className="text-text-tertiary font-mono text-[10px] break-all">{JSON.stringify(tc.args)}</div>
                    {tc.result && <div className="text-text-secondary mt-2 pl-2 border-l border-slate/30 max-h-40 overflow-y-auto whitespace-pre-wrap text-[10px] custom-scrollbar font-mono">{tc.result}</div>}
                  </div>
                ))}

                {/* Approvals */}
                {msg.approval && (
                  <div className={`my-3 p-3 border rounded-lg transition-all ${
                    msg.approval.resolved 
                      ? msg.approval.approved 
                        ? 'border-sage/40 bg-sage/5'
                        : 'border-terracotta/40 bg-terracotta/5'
                      : 'border-terracotta/50 bg-terracotta/5'
                  }`}>
                    <div className="flex justify-between items-center mb-2">
                      <div className={`font-bold text-sm font-display flex items-center gap-1.5 ${
                        msg.approval.resolved
                          ? msg.approval.approved
                            ? 'text-sage'
                            : 'text-terracotta'
                          : 'text-terracotta'
                      }`}>
                        {msg.approval.resolved ? (
                          msg.approval.approved ? (
                            <>
                              <CheckmarkCircle01Icon className="w-4 h-4" />
                              Tool Call Approved
                            </>
                          ) : (
                            <>
                              <Cancel01Icon className="w-4 h-4" />
                              Tool Call Denied
                            </>
                          )
                        ) : (
                          <>
                            <span className="animate-pulse">⚠️</span>
                            Tool Approval Required
                          </>
                        )}
                      </div>
                      <span className="text-[10px] uppercase font-display tracking-widest text-text-tertiary px-1.5 py-0.5 rounded bg-surface-2 border border-border-subtle">
                        {msg.approval.risk_level}
                      </span>
                    </div>

                    <div className="text-text-primary text-xs mb-2">
                      {msg.approval.resolved ? "The engine requested this command:" : "The engine wants to run this command:"}
                    </div>
                    <div className="bg-surface-2 p-2 rounded text-text-primary border border-border-subtle font-mono text-xs mb-3 truncate">
                      {msg.approval.tool_name}({JSON.stringify(msg.approval.arguments_preview || "")})
                    </div>
                    <div className="text-text-secondary text-xs italic mb-3">Reason: {msg.approval.reason}</div>
                    
                    {!msg.approval.resolved && (
                      <div className="flex gap-2">
                        <button 
                          onClick={() => handleApprove(msg.approval!.approval_id, true)}
                          className="flex-1 flex items-center justify-center gap-1 bg-sage/10 text-sage hover:bg-sage/20 border border-sage/20 py-1.5 rounded transition-colors font-display font-semibold"
                        >
                          <CheckmarkCircle01Icon className="w-4 h-4" /> Approve
                        </button>
                        <button 
                          onClick={() => handleApprove(msg.approval!.approval_id, false)}
                          className="flex-1 flex items-center justify-center gap-1 bg-terracotta/10 text-terracotta hover:bg-terracotta/20 border border-terracotta/20 py-1.5 rounded transition-colors font-display font-semibold"
                        >
                          <Cancel01Icon className="w-4 h-4" /> Deny
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {/* Cognitive Process */}
                {msg.processSteps && msg.processSteps.length > 0 && (
                  <details className="group mb-4 border border-border-subtle bg-surface-1 rounded-lg overflow-hidden">
                    <summary className="flex items-center gap-2 p-2 cursor-pointer text-xs font-semibold text-text-secondary hover:text-text-primary transition-colors bg-surface-2/20 list-none outline-none font-display">
                      <div className="flex-1 flex items-center gap-2">
                        <NeuralNetworkIcon className="w-4 h-4 text-slate" />
                        <span>Cognitive Process ({msg.processSteps.length} steps)</span>
                        {msg.thinking && !msg.content && !msg.approval && (
                          <span className="text-terracotta animate-pulse italic ml-2 text-[10px] inline-flex items-center gap-1">
                            <svg className="animate-spin h-2.5 w-2.5 text-terracotta" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                            {msg.thinking}
                          </span>
                        )}
                      </div>
                      <div className="transition-transform duration-200 group-open:rotate-180">▼</div>
                    </summary>
                    <div className="p-3 space-y-2 max-h-60 overflow-y-auto custom-scrollbar border-t border-border-subtle">
                      {msg.processSteps.map((step) => (
                        <div key={step.id} className="flex items-start gap-2 text-[11px]">
                          <span className={`px-1.5 py-0.5 rounded uppercase font-bold tracking-wider font-display ${
                            step.type === 'routing' ? 'bg-terracotta/10 text-terracotta' :
                            step.type === 'context' ? 'bg-slate/10 text-slate' :
                            'bg-sage/10 text-sage'
                          }`}>
                            {step.type}
                          </span>
                          <span className="text-text-secondary mt-0.5">{step.content}</span>
                        </div>
                      ))}
                    </div>
                  </details>
                )}

                {/* Thinking state fallback if no process steps */}
                {msg.thinking && !msg.processSteps?.length && !msg.approval?.resolved && (
                  <div className="text-terracotta animate-pulse italic text-xs mb-2 font-display flex items-center gap-1.5">
                    <svg className="animate-spin h-3.5 w-3.5 text-terracotta" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    {msg.thinking}
                  </div>
                )}

                {/* Error */}
                {msg.error && (
                  <div className="text-terracotta font-semibold mb-2">
                    {msg.error}
                  </div>
                )}

                {msg.cancelled && (
                  <div className="text-terracotta/80 italic mb-2 text-xs">
                    ⚠️ Request cancelled by user.
                  </div>
                )}

                {/* Initial generation loader before anything is streamed */}
                {!msg.content && !msg.thinking && (!msg.processSteps || msg.processSteps.length === 0) && !msg.error && !msg.cancelled && loading && msg.id === history[history.length - 1].id && (
                  <div className="flex items-center gap-2 text-text-tertiary mt-2">
                    <svg className="animate-spin h-4 w-4 text-terracotta" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <span className="text-xs font-display font-medium animate-pulse tracking-wide">Kinthic is thinking...</span>
                  </div>
                )}

                {/* Message Attachments */}
                {msg.attachments && msg.attachments.length > 0 && (
                  <div className="flex flex-wrap gap-2 mb-3">
                    {msg.attachments.map((att, idx) => (
                      <div key={idx} className="relative rounded-lg overflow-hidden border border-border-subtle max-w-[200px] shadow-sm bg-surface-2">
                        {att.type.startsWith('image/') ? (
                          <img src={att.url} className="max-h-32 w-auto object-cover rounded-lg" alt={att.name} />
                        ) : (
                          <div className="p-3 flex items-center gap-2 rounded text-xs font-mono">
                            <Attachment01Icon className="w-4 h-4 text-terracotta" />
                            <span className="text-text-primary truncate max-w-[120px]">{att.name}</span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {/* Markdown Content */}
                {msg.content && (
                  <div className="prose prose-invert prose-sm max-w-none prose-pre:p-0 prose-pre:bg-transparent font-display tracking-wide leading-relaxed">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        code({node, inline, className, children, ...props}: any) {
                          const match = /language-(\w+)/.exec(className || '')
                          return !inline && match ? (
                            <div className="my-4 overflow-hidden rounded-lg border border-border-strong/40 shadow-sm">
                              <div className="flex justify-between items-center px-4 py-2 bg-surface-2 text-text-secondary font-mono text-[10px] uppercase tracking-wider border-b border-border-subtle">
                                <span>{match[1]}</span>
                                <span className="opacity-40">code block</span>
                              </div>
                              <SyntaxHighlighter
                                {...props}
                                children={String(children).replace(/\n$/, '')}
                                style={atomDark}
                                language={match[1]}
                                PreTag="div"
                                customStyle={{ margin: 0, padding: '16px', background: '#1c1c1b', fontSize: '12px', fontFamily: 'var(--font-mono)' }}
                              />
                            </div>
                          ) : (
                            <code {...props} className={className + " bg-surface-2 px-1.5 py-0.5 rounded text-terracotta font-mono text-xs border border-border-subtle"}>
                              {children}
                            </code>
                          )
                        }
                      }}
                    >
                      {msg.content}
                    </ReactMarkdown>
                  </div>
                )}
              </div>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>

      <div className="relative">
        {/* Upload previews */}
        {attachments.length > 0 && (
          <div className="flex gap-2 p-2 mb-2 bg-surface-2 rounded-lg overflow-x-auto border border-border-subtle">
            {attachments.map((att, i) => (
              <div key={i} className="relative group flex-shrink-0">
                {att.file.type.startsWith('image/') ? (
                  <img src={att.url} className="w-16 h-16 object-cover rounded border border-border-subtle" alt="upload preview" />
                ) : (
                  <div className="w-16 h-16 flex items-center justify-center bg-surface-1 rounded border border-border-subtle text-[10px] text-text-secondary p-1 text-center overflow-hidden">
                    {att.file.name}
                  </div>
                )}
                <button 
                  onClick={() => setAttachments(prev => prev.filter((_, idx) => idx !== i))} 
                  className="absolute -top-2 -right-2 bg-terracotta rounded-full p-0.5 text-canvas opacity-0 group-hover:opacity-100 transition-opacity z-10"
                >
                  <Cancel01Icon className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="relative flex items-center">
          <input
            type="file"
            multiple
            className="hidden"
            ref={fileInputRef}
            onChange={handleFileSelect}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            className="absolute left-2 bottom-1.5 p-2 rounded hover:bg-surface-2 text-text-secondary hover:text-text-primary transition-colors z-10"
            title="Attach file"
          >
            <Attachment01Icon className="w-5 h-5" />
          </button>
          
          <TextareaAutosize
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Enter command or query (↑↓ for history, Shift+Enter for new line)..."
            className="w-full bg-surface-1 border border-border-subtle rounded-lg py-3 pl-12 pr-12 text-text-primary focus:outline-none focus:border-terracotta transition-colors resize-none custom-scrollbar font-display"
            minRows={1}
            maxRows={10}
            autoFocus
          />
          <button
            onClick={handleSend}
            disabled={loading || (!input.trim() && attachments.length === 0)}
            className="absolute right-2 bottom-1.5 p-2 rounded hover:bg-surface-2 text-text-secondary hover:text-terracotta disabled:opacity-50 transition-colors z-10"
          >
            <SentIcon className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  );
}
