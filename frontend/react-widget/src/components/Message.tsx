import React, { useMemo, useState } from 'react';
import { Bot, User, Copy, Check } from 'lucide-react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { ChatMessage } from '../config/defaults';
import { SourceBadge } from './SourceBadge';
import { ExecutionSteps } from './ExecutionSteps';
import { Loading } from './Loading';

export interface MessageProps {
  message: ChatMessage;
  showSources?: boolean;
  showExecutionSteps?: boolean;
}

export const Message: React.FC<MessageProps> = ({
  message,
  showSources = true,
  showExecutionSteps = true
}) => {
  const isUser = message.role === 'user';
  const [copied, setCopied] = useState<boolean>(false);

  // Format timestamp (e.g. 10:45 AM)
  const timeFormatted = useMemo(() => {
    try {
      return new Date(message.timestamp).toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return '';
    }
  }, [message.timestamp]);

  // Parse markdown and sanitize HTML safely
  const renderedHtml = useMemo(() => {
    if (!message.content) return '';
    try {
      const rawHtml = marked.parse(message.content, { async: false, gfm: true, breaks: true }) as string;
      return DOMPurify.sanitize(rawHtml, {
        ALLOWED_TAGS: [
          'p', 'b', 'i', 'em', 'strong', 'a', 'ul', 'ol', 'li', 'code', 'pre',
          'table', 'thead', 'tbody', 'tr', 'th', 'td', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'span'
        ],
        ALLOWED_ATTR: ['href', 'target', 'class', 'style', 'title']
      });
    } catch {
      return message.content;
    }
  }, [message.content]);

  const handleCopyMessage = async () => {
    if (!message.content) return;
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore
    }
  };

  return (
    <div className={`akb-message ${isUser ? 'akb-msg-user' : 'akb-msg-assistant'}`}>
      <div
        className={`akb-msg-avatar ${
          isUser ? 'akb-avatar-user' : 'akb-avatar-agent'
        }`}
      >
        {isUser ? <User size={16} /> : <Bot size={16} />}
      </div>

      <div className="akb-msg-body">
        {/* Execution steps for assistant */}
        {!isUser && showExecutionSteps && message.executionSteps && (
          <ExecutionSteps
            steps={message.executionSteps}
            isStreaming={message.status === 'streaming'}
          />
        )}

        <div className="akb-msg-bubble">
          {isUser ? (
            <p>{message.content}</p>
          ) : message.content ? (
            <div
              className="akb-markdown"
              dangerouslySetInnerHTML={{ __html: renderedHtml }}
            />
          ) : message.status === 'streaming' ? (
            <Loading currentStep={null} />
          ) : (
            <p style={{ color: 'var(--akb-text-muted)', fontStyle: 'italic' }}>
              No response generated.
            </p>
          )}

          {/* Sources cited */}
          {!isUser && showSources && (
            <SourceBadge
              sources={message.sources}
              databaseUsed={message.databaseUsed}
            />
          )}
        </div>

        <div className="akb-msg-meta">
          <span>{timeFormatted}</span>
          {!isUser && message.content && (
            <button
              type="button"
              className="akb-icon-btn"
              style={{ width: 22, height: 22 }}
              onClick={handleCopyMessage}
              title={copied ? 'Copied!' : 'Copy message text'}
              aria-label="Copy message"
            >
              {copied ? <Check size={12} color="var(--akb-accent-emerald)" /> : <Copy size={12} />}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
