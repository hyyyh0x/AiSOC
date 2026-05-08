'use client';

import { useEffect, useRef, useState } from 'react';

type MessageRole = 'user' | 'assistant' | 'system';

interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: string;
}

const QUICK_ACTIONS = [
  'Investigate Alert',
  'Summarize Case',
  'Find IOCs',
  'Check Reputation',
] as const;

const MOCK_RESPONSES: Record<string, string> = {
  'investigate alert':
    'Analyzing alert ALT-4092... Identified lateral movement from 10.0.3.17 to DC01. ' +
    'The source host has 3 prior alerts in the last 48h. ATT&CK mapping: T1021.002 (SMB/Admin Shares). ' +
    'Recommend isolating the host and resetting credentials for svc-backup.',
  'summarize case':
    'Case CS-2187 Summary:\n' +
    '- 7 correlated alerts across 3 hosts\n' +
    '- Timeline: initial access at 02:14 UTC, privilege escalation at 02:31 UTC, exfil attempt at 03:05 UTC\n' +
    '- Affected users: j.harlow, svc-backup\n' +
    '- Current status: containment in progress, 2 hosts isolated',
  'find iocs':
    'Found 3 related IOCs across 2 tenants:\n' +
    '1. IP 198.51.100.47 — C2 callback (confidence: 92%)\n' +
    '2. Hash e3b0c442...b855 — LockBit dropper (confidence: 95%)\n' +
    '3. Domain secure-login.example-phish.com — credential harvesting (confidence: 88%)\n\n' +
    'All three match STIX indicators published in the last 24h.',
  'check reputation':
    'Reputation check for 198.51.100.47:\n' +
    '- VirusTotal: 14/87 engines flagged malicious\n' +
    '- AbuseIPDB: reported 23 times, confidence 91%\n' +
    '- First seen: 2025-04-12, Last seen: active\n' +
    '- Associated campaigns: APT-42, Operation ShadowGate\n' +
    '- Recommendation: block at perimeter immediately',
};

function getMockResponse(input: string): string {
  const lower = input.toLowerCase();
  for (const [key, response] of Object.entries(MOCK_RESPONSES)) {
    if (lower.includes(key)) return response;
  }
  return (
    `Analyzing your query: "${input}"\n\n` +
    'Found 3 related IOCs across 2 tenants. Cross-referencing with MITRE ATT&CK framework... ' +
    'Identified techniques T1078.002, T1059.001, and T1071.001. ' +
    'Risk assessment: HIGH. Recommend reviewing the correlated timeline in the case view.'
  );
}

const CONTEXT = {
  caseId: 'CS-2187',
  alertCount: 7,
  iocsFound: 3,
  riskLevel: 'High',
};

export default function InvestigationChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'sys-0',
      role: 'system',
      content: 'Investigation session started. Ask questions or use quick actions below.',
      timestamp: new Date().toISOString(),
    },
  ]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length, isTyping]);

  const sendMessage = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || isTyping) return;

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: trimmed,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setIsTyping(true);

    setTimeout(() => {
      const assistantMsg: ChatMessage = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        content: getMockResponse(trimmed),
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
      setIsTyping(false);
    }, 500);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  return (
    <div className="flex h-[calc(100vh-7rem)] gap-4">
      {/* Main chat area */}
      <div className="flex flex-1 flex-col rounded-xl border border-slate-800/80 bg-slate-900/40">
        {/* Header */}
        <div className="border-b border-slate-800/80 px-4 py-3">
          <h1 className="text-base font-semibold text-white">Investigation Chat</h1>
          <p className="text-xs text-slate-400">
            AI-assisted threat investigation — ask about alerts, IOCs, or cases
          </p>
        </div>

        {/* Messages */}
        <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto p-4">
          <ul className="mx-auto max-w-3xl space-y-3">
            {messages.map((m) => {
              if (m.role === 'system') {
                return (
                  <li key={m.id} className="flex justify-center">
                    <span className="rounded-full bg-slate-800/50 px-3 py-1 text-xs text-slate-500">
                      {m.content}
                    </span>
                  </li>
                );
              }
              const isUser = m.role === 'user';
              return (
                <li key={m.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm ${
                      isUser
                        ? 'bg-blue-600/20 text-white ring-1 ring-blue-500/30'
                        : 'bg-slate-800/70 text-slate-100 ring-1 ring-slate-700/60'
                    }`}
                  >
                    {m.content}
                  </div>
                </li>
              );
            })}
            {isTyping && (
              <li className="flex justify-start">
                <div className="rounded-2xl bg-slate-800/70 px-4 py-3 ring-1 ring-slate-700/60">
                  <span className="inline-flex items-center gap-1 text-slate-400">
                    <span className="animate-pulse">●</span>
                    <span className="animate-pulse" style={{ animationDelay: '0.2s' }}>●</span>
                    <span className="animate-pulse" style={{ animationDelay: '0.4s' }}>●</span>
                  </span>
                </div>
              </li>
            )}
          </ul>
        </div>

        {/* Quick actions + input */}
        <div className="border-t border-slate-800/80 p-3">
          <div className="mx-auto flex max-w-3xl flex-wrap gap-2 pb-2">
            {QUICK_ACTIONS.map((action) => (
              <button
                key={action}
                onClick={() => sendMessage(action)}
                disabled={isTyping}
                className="rounded-full border border-slate-700/70 bg-slate-800/50 px-3 py-1.5 text-xs text-slate-300 transition-colors hover:border-blue-500/40 hover:bg-slate-700/60 hover:text-white disabled:opacity-50"
              >
                {action}
              </button>
            ))}
          </div>
          <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-xl border border-slate-700/70 bg-slate-950/40 p-2 focus-within:border-blue-500/50">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              rows={1}
              placeholder="Ask about an alert, IOC, or investigation…"
              className="flex-1 resize-none bg-transparent px-2 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none"
            />
            <button
              onClick={() => sendMessage(input)}
              disabled={!input.trim() || isTyping}
              className={`flex-none rounded-lg px-3 py-2 text-sm font-semibold transition-colors ${
                input.trim() && !isTyping
                  ? 'bg-blue-600 text-white hover:bg-blue-500'
                  : 'bg-slate-800 text-slate-500'
              }`}
            >
              Send
            </button>
          </div>
        </div>
      </div>

      {/* Context panel */}
      <aside className="hidden w-64 flex-col gap-4 rounded-xl border border-slate-800/80 bg-slate-900/40 p-4 lg:flex">
        <h2 className="text-sm font-semibold text-white">Investigation Context</h2>

        <div className="space-y-3">
          <div className="rounded-lg border border-slate-800/80 bg-slate-800/30 p-3">
            <p className="text-[11px] font-medium uppercase tracking-wider text-slate-500">
              Case ID
            </p>
            <p className="mt-1 font-mono text-sm text-white">{CONTEXT.caseId}</p>
          </div>

          <div className="rounded-lg border border-slate-800/80 bg-slate-800/30 p-3">
            <p className="text-[11px] font-medium uppercase tracking-wider text-slate-500">
              Alert Count
            </p>
            <p className="mt-1 text-2xl font-bold text-white">{CONTEXT.alertCount}</p>
          </div>

          <div className="rounded-lg border border-slate-800/80 bg-slate-800/30 p-3">
            <p className="text-[11px] font-medium uppercase tracking-wider text-slate-500">
              IOCs Found
            </p>
            <p className="mt-1 text-2xl font-bold text-amber-400">{CONTEXT.iocsFound}</p>
          </div>

          <div className="rounded-lg border border-slate-800/80 bg-slate-800/30 p-3">
            <p className="text-[11px] font-medium uppercase tracking-wider text-slate-500">
              Risk Level
            </p>
            <p className="mt-1 text-lg font-bold text-red-400">{CONTEXT.riskLevel}</p>
          </div>
        </div>

        <div className="mt-auto rounded-lg border border-slate-800/80 bg-slate-800/30 p-3">
          <p className="text-[11px] font-medium uppercase tracking-wider text-slate-500">
            Session
          </p>
          <p className="mt-1 text-xs text-slate-400">
            {messages.filter((m) => m.role === 'user').length} messages sent
          </p>
          <p className="text-xs text-slate-400">
            {messages.filter((m) => m.role === 'assistant').length} AI responses
          </p>
        </div>
      </aside>
    </div>
  );
}
