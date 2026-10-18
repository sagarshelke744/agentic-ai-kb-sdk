import React, { useRef, useEffect, useState } from 'react';
import { Sparkles, ArrowDown, ArrowRight } from 'lucide-react';
import { ChatMessage } from '../config/defaults';
import { Message } from './Message';
import { InputBox } from './InputBox';

export interface ChatWindowProps {
  messages: ChatMessage[];
  isLoading: boolean;
  isStreaming: boolean;
  welcomeMessage: string;
  suggestedPrompts?: string[];
  showSources?: boolean;
  showExecutionSteps?: boolean;
  onSendMessage: (text: string) => void;
  onStopStreaming: () => void;
  onRetry?: (messageId: string) => void;
}

export const ChatWindow: React.FC<ChatWindowProps> = ({
  messages,
  isLoading,
  isStreaming,
  welcomeMessage,
  suggestedPrompts = [],
  showSources = true,
  showExecutionSteps = true,
  onSendMessage,
  onStopStreaming,
  onRetry
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [showScrollBottom, setShowScrollBottom] = useState<boolean>(false);
  const userScrolledUpRef = useRef<boolean>(false);

  // Auto scroll to bottom when messages or content change
  useEffect(() => {
    const el = containerRef.current;
    if (!el || userScrolledUpRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, isStreaming]);

  const handleScroll = () => {
    const el = containerRef.current;
    if (!el) return;
    const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
    userScrolledUpRef.current = !isAtBottom;
    setShowScrollBottom(!isAtBottom);
  };

  const scrollToBottom = () => {
    const el = containerRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    userScrolledUpRef.current = false;
    setShowScrollBottom(false);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, position: 'relative' }}>
      <div
        ref={containerRef}
        className="akb-messages-container"
        onScroll={handleScroll}
      >
        {messages.length === 0 ? (
          <div className="akb-empty-state">
            <div className="akb-empty-icon">
              <Sparkles size={28} />
            </div>
            <h3 className="akb-empty-title">Enterprise Knowledge Assistant</h3>
            <p className="akb-empty-desc">{welcomeMessage}</p>

            {suggestedPrompts && suggestedPrompts.length > 0 && (
              <div className="akb-prompts-grid">
                {suggestedPrompts.map((prompt, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className="akb-prompt-pill"
                    onClick={() => onSendMessage(prompt)}
                  >
                    <span>{prompt}</span>
                    <ArrowRight size={14} color="var(--akb-primary)" />
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          messages.map((msg) => (
            <Message
              key={msg.id}
              message={msg}
              showSources={showSources}
              showExecutionSteps={showExecutionSteps}
              onRetry={onRetry}
            />
          ))
        )}
      </div>

      {showScrollBottom && (
        <button
          type="button"
          className="akb-scroll-bottom-btn"
          onClick={scrollToBottom}
          title="Scroll to bottom"
          aria-label="Scroll to bottom"
        >
          <ArrowDown size={16} />
        </button>
      )}

      <InputBox
        onSend={onSendMessage}
        onStop={onStopStreaming}
        isLoading={isLoading}
        isStreaming={isStreaming}
      />
    </div>
  );
};
