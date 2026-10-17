import React, { useState, useRef, useEffect } from 'react';
import { ArrowUp, Square } from 'lucide-react';

export interface InputBoxProps {
  onSend: (message: string) => void;
  onStop?: () => void;
  isLoading: boolean;
  isStreaming: boolean;
  placeholder?: string;
}

export const InputBox: React.FC<InputBoxProps> = ({
  onSend,
  onStop,
  isLoading,
  isStreaming,
  placeholder = 'Ask anything about your database...'
}) => {
  const [text, setText] = useState<string>('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea height
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, [text]);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (isStreaming) {
      onStop?.();
      return;
    }
    const trimmed = text.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setText('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="akb-input-container">
      <form onSubmit={handleSubmit} className="akb-input-wrapper">
        <textarea
          ref={textareaRef}
          className="akb-textarea"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          rows={1}
          disabled={isLoading && !isStreaming}
          aria-label="Ask a question"
        />

        {isStreaming ? (
          <button
            type="button"
            className="akb-send-btn akb-stop-btn"
            onClick={onStop}
            title="Stop generating"
            aria-label="Stop generating"
          >
            <Square size={14} fill="currentColor" />
          </button>
        ) : (
          <button
            type="submit"
            className="akb-send-btn"
            disabled={!text.trim() || isLoading}
            title="Send query"
            aria-label="Send query"
          >
            <ArrowUp size={18} strokeWidth={2.4} />
          </button>
        )}
      </form>

      <div className="akb-footer-bar">
        <span>Press Enter to send, Shift+Enter for new line</span>
        <span>Grounded with SQL AST</span>
      </div>
    </div>
  );
};
