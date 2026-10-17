import React from 'react';
import { Database, Moon, Sun, Trash2, X, Minus } from 'lucide-react';

export interface HeaderProps {
  title: string;
  subtitle?: string;
  theme: 'dark' | 'light';
  onToggleTheme: () => void;
  onClearHistory: () => void;
  onMinimize?: () => void;
  onClose?: () => void;
  isStreaming?: boolean;
  isFloating?: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  title,
  subtitle,
  theme,
  onToggleTheme,
  onClearHistory,
  onMinimize,
  onClose,
  isStreaming = false,
  isFloating = true
}) => {
  return (
    <header className="akb-header">
      <div className="akb-header-left">
        <div className="akb-avatar" aria-label="Assistant Avatar">
          <Database size={20} strokeWidth={2.2} />
          <span
            className="akb-status-indicator"
            style={{
              backgroundColor: isStreaming ? 'var(--akb-accent-cyan)' : 'var(--akb-accent-emerald)',
              boxShadow: isStreaming
                ? '0 0 8px var(--akb-accent-cyan)'
                : '0 0 6px var(--akb-accent-emerald)'
            }}
            title={isStreaming ? 'Streaming response...' : 'Online & Ready'}
          />
        </div>
        <div className="akb-header-info">
          <h2 className="akb-header-title">{title}</h2>
          {subtitle && <p className="akb-header-subtitle">{subtitle}</p>}
        </div>
      </div>

      <div className="akb-header-actions">
        <button
          type="button"
          className="akb-icon-btn"
          onClick={onToggleTheme}
          title={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} mode`}
          aria-label="Toggle Theme"
        >
          {theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
        </button>

        <button
          type="button"
          className="akb-icon-btn"
          onClick={onClearHistory}
          title="Clear Conversation History"
          aria-label="Clear History"
        >
          <Trash2 size={17} />
        </button>

        {isFloating && onMinimize && (
          <button
            type="button"
            className="akb-icon-btn"
            onClick={onMinimize}
            title="Minimize"
            aria-label="Minimize Chat"
          >
            <Minus size={17} />
          </button>
        )}

        {isFloating && onClose && (
          <button
            type="button"
            className="akb-icon-btn"
            onClick={onClose}
            title="Close Chat"
            aria-label="Close Chat"
          >
            <X size={18} />
          </button>
        )}
      </div>
    </header>
  );
};
