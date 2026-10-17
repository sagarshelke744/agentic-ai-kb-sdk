import React, { useState, useEffect } from 'react';
import { AgenticChatbot } from './components/AgenticChatbot';
import { Database, ShieldCheck, Zap, Layers, Sparkles, Server } from 'lucide-react';
import './styles/widget.css';

export const App: React.FC = () => {
  const [apiUrl, setApiUrl] = useState<string>('http://localhost:8000');
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  const [position, setPosition] = useState<'bottom-right' | 'bottom-left'>('bottom-right');
  const [enableStreaming, setEnableStreaming] = useState<boolean>(true);
  const [showSources, setShowSources] = useState<boolean>(true);
  const [showExecutionSteps, setShowExecutionSteps] = useState<boolean>(true);
  const [assistantName, setAssistantName] = useState<string>('Data Assistant');
  const [isServerHealthy, setIsServerHealthy] = useState<boolean | null>(null);

  // Ping backend API health
  useEffect(() => {
    let isMounted = true;
    const check = async () => {
      try {
        const res = await fetch(`${apiUrl.replace(/\/+$/, '')}/api/v1/health`);
        if (isMounted) setIsServerHealthy(res.ok);
      } catch {
        if (isMounted) setIsServerHealthy(false);
      }
    };
    check();
    const interval = setInterval(check, 10000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [apiUrl]);

  return (
    <div
      style={{
        minHeight: '100vh',
        background: theme === 'dark' ? '#070a10' : '#f8fafc',
        color: theme === 'dark' ? '#f1f5f9' : '#0f172a',
        fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
        padding: '40px 24px',
        transition: 'background 0.3s ease'
      }}
    >
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>
        {/* Hero Header */}
        <div style={{ textAlign: 'center', marginBottom: 48 }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              padding: '6px 16px',
              borderRadius: 9999,
              background: theme === 'dark' ? 'rgba(99, 102, 241, 0.15)' : 'rgba(79, 70, 229, 0.1)',
              border: `1px solid ${theme === 'dark' ? 'rgba(99, 102, 241, 0.3)' : 'rgba(79, 70, 229, 0.2)'}`,
              color: '#6366f1',
              fontSize: 13,
              fontWeight: 600,
              marginBottom: 16
            }}
          >
            <Sparkles size={14} />
            <span>Agentic KnowledgeBase SDK • Phase 8 & 9 Frontend</span>
          </div>

          <h1
            style={{
              fontSize: '2.8rem',
              fontWeight: 800,
              letterSpacing: '-0.03em',
              marginBottom: 14,
              background: 'linear-gradient(135deg, #6366f1 0%, #a855f7 50%, #ec4899 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent'
            }}
          >
            Enterprise AI Database Chatbot
          </h1>

          <p
            style={{
              fontSize: '1.15rem',
              color: theme === 'dark' ? '#94a3b8' : '#64748b',
              maxWidth: 680,
              margin: '0 auto',
              lineHeight: 1.6
            }}
          >
            Grounded Natural-Language-to-SQL over enterprise schemas with live AST validation,
            semantic metric retrieval, and real-time SSE streaming.
          </p>

          {/* Backend Status Badge */}
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              marginTop: 18,
              padding: '4px 14px',
              borderRadius: 20,
              fontSize: 12,
              background: theme === 'dark' ? '#111827' : '#ffffff',
              border: `1px solid ${theme === 'dark' ? '#1f2937' : '#e2e8f0'}`
            }}
          >
            <Server size={14} color="#94a3b8" />
            <span>FastAPI Server:</span>
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background:
                  isServerHealthy === true
                    ? '#10b981'
                    : isServerHealthy === false
                    ? '#ef4444'
                    : '#f59e0b',
                display: 'inline-block'
              }}
            />
            <span style={{ fontWeight: 600 }}>
              {isServerHealthy === true
                ? 'Online (localhost:8000)'
                : isServerHealthy === false
                ? 'Offline (start server with agentic-kb serve)'
                : 'Checking...'}
            </span>
          </div>
        </div>

        {/* Feature Highlights Grid */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
            gap: 20,
            marginBottom: 48
          }}
        >
          <div
            style={{
              padding: 22,
              borderRadius: 16,
              background: theme === 'dark' ? '#111827' : '#ffffff',
              border: `1px solid ${theme === 'dark' ? 'rgba(255,255,255,0.08)' : '#e2e8f0'}`,
              boxShadow: '0 4px 20px rgba(0,0,0,0.06)'
            }}
          >
            <div style={{ color: '#6366f1', marginBottom: 12 }}>
              <ShieldCheck size={28} />
            </div>
            <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 6 }}>AST-Enforced Security</h3>
            <p style={{ fontSize: 13, color: '#94a3b8', lineHeight: 1.5 }}>
              Guaranteed SELECT-only execution, column/table allowlists, and automatic Row-Level Security injection.
            </p>
          </div>

          <div
            style={{
              padding: 22,
              borderRadius: 16,
              background: theme === 'dark' ? '#111827' : '#ffffff',
              border: `1px solid ${theme === 'dark' ? 'rgba(255,255,255,0.08)' : '#e2e8f0'}`,
              boxShadow: '0 4px 20px rgba(0,0,0,0.06)'
            }}
          >
            <div style={{ color: '#06b6d4', marginBottom: 12 }}>
              <Database size={28} />
            </div>
            <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 6 }}>Source Citations</h3>
            <p style={{ fontSize: 13, color: '#94a3b8', lineHeight: 1.5 }}>
              Transparent table and schema citations showing precisely which database objects answered the prompt.
            </p>
          </div>

          <div
            style={{
              padding: 22,
              borderRadius: 16,
              background: theme === 'dark' ? '#111827' : '#ffffff',
              border: `1px solid ${theme === 'dark' ? 'rgba(255,255,255,0.08)' : '#e2e8f0'}`,
              boxShadow: '0 4px 20px rgba(0,0,0,0.06)'
            }}
          >
            <div style={{ color: '#10b981', marginBottom: 12 }}>
              <Zap size={28} />
            </div>
            <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 6 }}>Real-Time SSE Stream</h3>
            <p style={{ fontSize: 13, color: '#94a3b8', lineHeight: 1.5 }}>
              Step-by-step reasoning progress and streaming token response with instant cancellation.
            </p>
          </div>

          <div
            style={{
              padding: 22,
              borderRadius: 16,
              background: theme === 'dark' ? '#111827' : '#ffffff',
              border: `1px solid ${theme === 'dark' ? 'rgba(255,255,255,0.08)' : '#e2e8f0'}`,
              boxShadow: '0 4px 20px rgba(0,0,0,0.06)'
            }}
          >
            <div style={{ color: '#d946ef', marginBottom: 12 }}>
              <Layers size={28} />
            </div>
            <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 6 }}>Dual Deployment</h3>
            <p style={{ fontSize: 13, color: '#94a3b8', lineHeight: 1.5 }}>
              Import directly in React apps or embed as a single script tag via <code>AgenticKB.init()</code>.
            </p>
          </div>
        </div>

        {/* Live Widget Configuration Playground */}
        <div
          style={{
            padding: 28,
            borderRadius: 20,
            background: theme === 'dark' ? '#111827' : '#ffffff',
            border: `1px solid ${theme === 'dark' ? 'rgba(255,255,255,0.08)' : '#e2e8f0'}`,
            marginBottom: 40
          }}
        >
          <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 20 }}>Widget Configuration Controls</h2>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 6, color: '#94a3b8' }}>
                API URL
              </label>
              <input
                type="text"
                value={apiUrl}
                onChange={(e) => setApiUrl(e.target.value)}
                style={{
                  width: '100%',
                  padding: '9px 12px',
                  borderRadius: 8,
                  border: '1px solid rgba(255,255,255,0.1)',
                  background: theme === 'dark' ? '#0b0f17' : '#f8fafc',
                  color: 'inherit',
                  fontSize: 13
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 6, color: '#94a3b8' }}>
                Assistant Name
              </label>
              <input
                type="text"
                value={assistantName}
                onChange={(e) => setAssistantName(e.target.value)}
                style={{
                  width: '100%',
                  padding: '9px 12px',
                  borderRadius: 8,
                  border: '1px solid rgba(255,255,255,0.1)',
                  background: theme === 'dark' ? '#0b0f17' : '#f8fafc',
                  color: 'inherit',
                  fontSize: 13
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 6, color: '#94a3b8' }}>
                Position
              </label>
              <select
                value={position}
                onChange={(e) => setPosition(e.target.value as 'bottom-right' | 'bottom-left')}
                style={{
                  width: '100%',
                  padding: '9px 12px',
                  borderRadius: 8,
                  border: '1px solid rgba(255,255,255,0.1)',
                  background: theme === 'dark' ? '#0b0f17' : '#f8fafc',
                  color: 'inherit',
                  fontSize: 13
                }}
              >
                <option value="bottom-right">Bottom Right</option>
                <option value="bottom-left">Bottom Left</option>
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 6, color: '#94a3b8' }}>
                Theme
              </label>
              <button
                type="button"
                onClick={() => setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'))}
                style={{
                  width: '100%',
                  padding: '9px 12px',
                  borderRadius: 8,
                  border: '1px solid rgba(255,255,255,0.1)',
                  background: theme === 'dark' ? '#0b0f17' : '#f8fafc',
                  color: 'inherit',
                  fontSize: 13,
                  cursor: 'pointer',
                  fontWeight: 600
                }}
              >
                Switch to {theme === 'dark' ? 'Light' : 'Dark'} Mode
              </button>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 24, marginTop: 18, flexWrap: 'wrap' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={enableStreaming}
                onChange={(e) => setEnableStreaming(e.target.checked)}
              />
              <span>Enable SSE Streaming</span>
            </label>

            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={showSources}
                onChange={(e) => setShowSources(e.target.checked)}
              />
              <span>Show Source Citations</span>
            </label>

            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={showExecutionSteps}
                onChange={(e) => setShowExecutionSteps(e.target.checked)}
              />
              <span>Show Reasoning Steps</span>
            </label>
          </div>
        </div>

        {/* Integration Code Snippet */}
        <div
          style={{
            padding: 24,
            borderRadius: 16,
            background: theme === 'dark' ? '#0b0f17' : '#ffffff',
            border: `1px solid ${theme === 'dark' ? 'rgba(255,255,255,0.08)' : '#e2e8f0'}`,
            fontSize: 13
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: 8, color: '#6366f1' }}>
            Quick HTML Script Integration (Phase 9)
          </div>
          <pre
            style={{
              padding: 14,
              borderRadius: 8,
              background: theme === 'dark' ? '#06080d' : '#f1f5f9',
              color: '#38bdf8',
              overflowX: 'auto',
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 12
            }}
          >
            {`<script src="https://cdn.example.com/agentic-kb-widget.js"></script>\n<script>\n  AgenticKB.init({\n    apiUrl: "${apiUrl}",\n    assistantName: "${assistantName}",\n    theme: "${theme}",\n    position: "${position}"\n  });\n</script>`}
          </pre>
        </div>
      </div>

      {/* Floating Widget Instance */}
      <AgenticChatbot
        apiUrl={apiUrl}
        assistantName={assistantName}
        theme={theme}
        position={position}
        enableStreaming={enableStreaming}
        showSources={showSources}
        showExecutionSteps={showExecutionSteps}
        isOpenDefault={false}
      />
    </div>
  );
};

export default App;
