import React, { useState, useEffect } from 'react';
import { MessageSquare, X } from 'lucide-react';
import { ChatbotConfig, DEFAULT_CONFIG } from '../config/defaults';
import { useChat } from '../hooks/useChat';
import { Header } from './Header';
import { ChatWindow } from './ChatWindow';
import '../styles/widget.css';

export interface AgenticChatbotProps extends Partial<ChatbotConfig> {
  onOpenChange?: (isOpen: boolean) => void;
}

export const AgenticChatbot: React.FC<AgenticChatbotProps> = (props) => {
  const mergedConfig: ChatbotConfig = {
    ...DEFAULT_CONFIG,
    ...props
  };

  const isFloating = mergedConfig.isFloating ?? true;
  const [isOpen, setIsOpen] = useState<boolean>(
    isFloating ? Boolean(mergedConfig.isOpenDefault) : true
  );
  const [isMinimized, setIsMinimized] = useState<boolean>(false);
  const [theme, setTheme] = useState<'dark' | 'light'>(
    mergedConfig.theme === 'light' ? 'light' : 'dark'
  );

  const {
    messages,
    isLoading,
    isStreaming,
    sendMessage,
    stopStreaming,
    clearHistory
  } = useChat(mergedConfig);

  // Notify parent on open change
  useEffect(() => {
    props.onOpenChange?.(isOpen);
  }, [isOpen, props]);

  const toggleOpen = () => {
    if (isMinimized) {
      setIsMinimized(false);
      setIsOpen(true);
    } else {
      setIsOpen(!isOpen);
    }
  };

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  };

  const positionClass = `akb-pos-${mergedConfig.position || 'bottom-right'}`;
  const unreadCount = !isOpen && messages.length > 0 ? messages.filter((m) => m.role === 'assistant').length : 0;

  return (
    <div
      className={`akb-root akb-theme-${theme}`}
      style={mergedConfig.primaryColor ? ({ '--akb-primary': mergedConfig.primaryColor } as React.CSSProperties) : undefined}
    >
      {/* Floating Launcher Button */}
      {isFloating && (
        <div className={`akb-launcher-container ${positionClass}`}>
          <button
            type="button"
            className="akb-launcher-btn"
            onClick={toggleOpen}
            aria-label={isOpen ? 'Close Assistant' : 'Open KnowledgeBase Assistant'}
            title={isOpen ? 'Close Assistant' : 'Ask Database Assistant'}
          >
            <div className="akb-pulse-ring" />
            {isOpen ? (
              <X className="akb-launcher-icon" size={26} />
            ) : (
              <MessageSquare className="akb-launcher-icon" size={26} />
            )}
            {unreadCount > 0 && <span className="akb-unread-badge">{unreadCount}</span>}
          </button>
        </div>
      )}

      {/* Main Chat Window */}
      {(isOpen || !isFloating) && (
        <div
          className={`akb-window ${isFloating ? 'akb-floating' : 'akb-embedded'} ${
            isFloating ? positionClass : ''
          } ${isMinimized ? 'akb-minimized' : ''}`}
        >
          <Header
            title={mergedConfig.assistantName || 'Data Assistant'}
            subtitle={mergedConfig.assistantSubtitle}
            theme={theme}
            onToggleTheme={toggleTheme}
            onClearHistory={clearHistory}
            onMinimize={isFloating ? () => setIsMinimized(!isMinimized) : undefined}
            onClose={isFloating ? () => setIsOpen(false) : undefined}
            isStreaming={isStreaming}
            isFloating={isFloating}
          />

          {!isMinimized && (
            <ChatWindow
              messages={messages}
              isLoading={isLoading}
              isStreaming={isStreaming}
              welcomeMessage={mergedConfig.welcomeMessage || DEFAULT_CONFIG.welcomeMessage}
              suggestedPrompts={mergedConfig.suggestedPrompts}
              showSources={mergedConfig.showSources}
              showExecutionSteps={mergedConfig.showExecutionSteps}
              onSendMessage={sendMessage}
              onStopStreaming={stopStreaming}
            />
          )}
        </div>
      )}
    </div>
  );
};
