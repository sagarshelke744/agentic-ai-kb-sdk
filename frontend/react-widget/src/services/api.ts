/**
 * API Service for communicating with the Agentic KnowledgeBase FastAPI backend.
 */

import { ChatbotConfig, ExecutionStep } from '../config/defaults';

export interface ChatResponse {
  answer: string;
  requestId: string;
  sessionId: string;
  metadata?: {
    database_used?: boolean;
    tables_used?: string[];
    sources?: string[];
    execution_time_ms?: number;
    tokens_used?: number;
  };
}

export class StreamError extends Error {
  code?: string;
  retryable: boolean;
  constructor(message: string, code?: string, retryable = false) {
    super(message);
    this.name = 'StreamError';
    this.code = code;
    this.retryable = retryable;
  }
}

export interface StreamCallbacks {
  onStep?: (step: ExecutionStep) => void;
  onToken?: (token: string) => void;
  onComplete?: (response: ChatResponse) => void;
  onError?: (error: Error) => void;
}

export class ChatApiService {
  private config: ChatbotConfig;

  constructor(config: ChatbotConfig) {
    this.config = config;
  }

  public updateConfig(config: ChatbotConfig) {
    this.config = config;
  }

  private getHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'Accept': 'application/json'
    };
    if (this.config.apiKey) {
      headers['X-API-Key'] = this.config.apiKey;
    }
    if (this.config.tenantId) {
      headers['X-Tenant-ID'] = this.config.tenantId;
    }
    if (this.config.userId) {
      headers['X-User-ID'] = this.config.userId;
    }
    return headers;
  }

  /**
   * Synchronous chat request (non-streaming)
   */
  public async sendChat(
    message: string,
    sessionId: string,
    signal?: AbortSignal
  ): Promise<ChatResponse> {
    const url = `${this.config.apiUrl.replace(/\/+$/, '')}/api/v1/chat`;
    const payload = {
      message,
      conversation_id: sessionId,
      stream: false,
      user_id: this.config.userId,
      tenant_id: this.config.tenantId
    };

    const response = await fetch(url, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify(payload),
      signal
    });

    if (!response.ok) {
      const errorText = await response.text();
      let errorMsg = `Server returned status ${response.status}`;
      try {
        const parsed = JSON.parse(errorText);
        if (parsed.detail) errorMsg = parsed.detail;
      } catch {
        if (errorText) errorMsg = errorText;
      }
      throw new Error(errorMsg);
    }

    const data = await response.json();
    return {
      answer: data.answer,
      requestId: data.request_id || '',
      sessionId: data.session_id || sessionId,
      metadata: data.metadata
    };
  }

  /**
   * Streaming chat request using Server-Sent Events (SSE)
   */
  public async streamChat(
    message: string,
    sessionId: string,
    callbacks: StreamCallbacks,
    signal?: AbortSignal
  ): Promise<void> {
    const url = `${this.config.apiUrl.replace(/\/+$/, '')}/api/v1/chat/stream`;
    const payload = {
      message,
      conversation_id: sessionId,
      stream: true,
      user_id: this.config.userId,
      tenant_id: this.config.tenantId
    };

    const headers = this.getHeaders();
    headers['Accept'] = 'text/event-stream';

    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
      signal
    });

    if (!response.ok) {
      const errorText = await response.text();
      let errorMsg = `Stream request failed with status ${response.status}`;
      try {
        const parsed = JSON.parse(errorText);
        if (parsed.detail) errorMsg = parsed.detail;
      } catch {
        if (errorText) errorMsg = errorText;
      }
      throw new Error(errorMsg);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('Streaming response body is not readable.');
    }

    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let finished = false;

    const stepId = () => `step-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`;

    // Route one parsed SSE event (name + JSON payload) to the callbacks
    const dispatch = (eventName: string, event: Record<string, any>) => {
      const type = eventName || event.type;
      if (type === 'step') {
        callbacks.onStep?.({
          id: stepId(),
          name: event.message || event.step || 'Processing...',
          status: 'running',
          timestamp: event.timestamp || Date.now()
        });
      } else if (type === 'retry') {
        callbacks.onStep?.({
          id: stepId(),
          name: `AI service busy — retrying in ${Math.ceil(event.wait_seconds ?? 0)}s (attempt ${event.attempt}/${event.max_retries})`,
          status: 'warning',
          timestamp: Date.now()
        });
      } else if (type === 'token') {
        callbacks.onToken?.(event.text ?? event.token ?? '');
      } else if (type === 'done' || type === 'final') {
        finished = true;
        callbacks.onComplete?.({
          answer: event.answer || '',
          requestId: event.request_id || '',
          sessionId: event.conversation_id || event.session_id || sessionId,
          metadata: event.metadata
        });
      } else if (type === 'error') {
        finished = true;
        callbacks.onError?.(
          new StreamError(
            event.message || event.user_safe_message || 'Stream error occurred',
            event.code,
            Boolean(event.retryable)
          )
        );
      }
    };

    const processBlock = (block: string) => {
      let eventName = '';
      const dataLines: string[] = [];
      for (const rawLine of block.split('\n')) {
        const line = rawLine.replace(/\r$/, '');
        if (!line || line.startsWith(':')) continue; // heartbeat / comment
        if (line.startsWith('event:')) eventName = line.slice(6).trim();
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
      }
      const jsonStr = dataLines.join('\n');
      if (!jsonStr || jsonStr === '[DONE]') return;
      try {
        dispatch(eventName, JSON.parse(jsonStr));
      } catch (err) {
        console.warn('Failed to parse SSE event chunk:', jsonStr, err);
      }
    };

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        // SSE events are separated by a blank line (LF or CRLF)
        const blocks = buffer.split(/\r?\n\r?\n/);
        buffer = blocks.pop() || '';
        for (const block of blocks) processBlock(block);
      }
      if (buffer.trim()) processBlock(buffer);
    } finally {
      reader.releaseLock();
    }

    if (!finished) {
      throw new StreamError('The connection closed before the answer was complete.', 'StreamInterrupted', true);
    }
  }

  /**
   * Check API health
   */
  public async checkHealth(): Promise<boolean> {
    try {
      const url = `${this.config.apiUrl.replace(/\/+$/, '')}/api/v1/health`;
      const res = await fetch(url, { headers: this.getHeaders() });
      return res.ok;
    } catch {
      return false;
    }
  }
}
