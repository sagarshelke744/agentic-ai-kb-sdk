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
    execution_time_ms?: number;
    tokens_used?: number;
  };
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

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        // keep the last incomplete chunk in the buffer
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || trimmed.startsWith(':')) {
            // Heartbeat or comment
            continue;
          }

          if (trimmed.startsWith('data:')) {
            const jsonStr = trimmed.slice(5).trim();
            if (jsonStr === '[DONE]') {
              continue;
            }

            try {
              const event = JSON.parse(jsonStr);

              if (event.type === 'step') {
                callbacks.onStep?.({
                  id: `step-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`,
                  name: event.step || 'Processing...',
                  status: 'running',
                  timestamp: event.timestamp || Date.now()
                });
              } else if (event.type === 'token') {
                callbacks.onToken?.(event.token || '');
              } else if (event.type === 'final') {
                callbacks.onComplete?.({
                  answer: event.answer || '',
                  requestId: event.request_id || '',
                  sessionId: event.session_id || sessionId,
                  metadata: event.metadata
                });
              } else if (event.type === 'error') {
                callbacks.onError?.(new Error(event.message || 'Stream error occurred'));
              }
            } catch (err) {
              console.warn('Failed to parse SSE event chunk:', jsonStr, err);
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
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
