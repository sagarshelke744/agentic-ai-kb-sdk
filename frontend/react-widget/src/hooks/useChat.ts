/**
 * Custom React Hook for Managing Agentic Chat State, Streaming, and History
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { ChatbotConfig, ChatMessage, ExecutionStep, DEFAULT_CONFIG } from '../config/defaults';
import { ChatApiService, ChatResponse, StreamError } from '../services/api';

export function useChat(userConfig: ChatbotConfig) {
  const config = { ...DEFAULT_CONFIG, ...userConfig };
  const apiServiceRef = useRef<ChatApiService>(new ChatApiService(config));
  const abortControllerRef = useRef<AbortController | null>(null);

  // Generate or restore session ID
  const [sessionId, setSessionId] = useState<string>(() => {
    if (config.persistSession && typeof window !== 'undefined') {
      const saved = sessionStorage.getItem('akb_session_id');
      if (saved) return saved;
    }
    const newId = `session-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    if (config.persistSession && typeof window !== 'undefined') {
      sessionStorage.setItem('akb_session_id', newId);
    }
    return newId;
  });

  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    if (config.persistSession && typeof window !== 'undefined') {
      const saved = sessionStorage.getItem('akb_messages');
      if (saved) {
        try {
          return JSON.parse(saved);
        } catch {
          // ignore corrupted storage
        }
      }
    }
    return [];
  });

  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [currentStep, setCurrentStep] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Sync API config when userConfig changes
  useEffect(() => {
    apiServiceRef.current.updateConfig({ ...DEFAULT_CONFIG, ...userConfig });
  }, [userConfig]);

  // Persist messages in sessionStorage
  useEffect(() => {
    if (config.persistSession && typeof window !== 'undefined') {
      sessionStorage.setItem('akb_messages', JSON.stringify(messages));
    }
  }, [messages, config.persistSession]);

  const stopStreaming = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsStreaming(false);
    setIsLoading(false);
    setCurrentStep(null);
  }, []);

  const clearHistory = useCallback(() => {
    stopStreaming();
    setMessages([]);
    setError(null);
    const newId = `session-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    setSessionId(newId);
    if (config.persistSession && typeof window !== 'undefined') {
      sessionStorage.removeItem('akb_messages');
      sessionStorage.setItem('akb_session_id', newId);
    }
  }, [config.persistSession, stopStreaming]);

  // Record a failed response: close out running steps and attach a structured error to the message
  const markStreamFailed = useCallback((messageId: string, err: Error) => {
    const streamErr = err instanceof StreamError ? err : null;
    const message =
      streamErr?.message ||
      (err instanceof TypeError
        ? 'Could not reach the server. Please check your connection and try again.'
        : err.message || 'Something went wrong while processing your request.');
    const retryable = streamErr ? streamErr.retryable : err instanceof TypeError;
    setError(message);
    setMessages((prev) =>
      prev.map((m) => {
        if (m.id !== messageId) return m;
        return {
          ...m,
          status: 'error',
          executionSteps: (m.executionSteps || []).map((st) =>
            st.status === 'running' ? { ...st, status: 'failed' as const } : st
          ),
          error: { message, code: streamErr?.code, retryable }
        };
      })
    );
  }, []);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isLoading || isStreaming) return;

      setError(null);
      const userMessageId = `msg-${Date.now()}-u`;
      const assistantMessageId = `msg-${Date.now() + 1}-a`;

      const userMsg: ChatMessage = {
        id: userMessageId,
        role: 'user',
        content: trimmed,
        timestamp: Date.now()
      };

      const initialAssistantMsg: ChatMessage = {
        id: assistantMessageId,
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
        executionSteps: [],
        sources: [],
        status: 'streaming'
      };

      setMessages((prev) => [...prev, userMsg, initialAssistantMsg]);
      setIsLoading(true);

      const abortController = new AbortController();
      abortControllerRef.current = abortController;

      if (config.enableStreaming) {
        setIsStreaming(true);
        setCurrentStep('Initializing query...');

        try {
          await apiServiceRef.current.streamChat(
            trimmed,
            sessionId,
            {
              onStep: (step: ExecutionStep) => {
                setCurrentStep(step.name);
                setMessages((prev) =>
                  prev.map((m) => {
                    if (m.id !== assistantMessageId) return m;
                    const existing = m.executionSteps || [];
                    // Mark previous running steps as completed
                    const updated = existing.map((s) =>
                      s.status === 'running' ? { ...s, status: 'completed' as const } : s
                    );
                    return {
                      ...m,
                      executionSteps: [...updated, step]
                    };
                  })
                );
              },
              onToken: (token: string) => {
                setMessages((prev) =>
                  prev.map((m) => {
                    if (m.id !== assistantMessageId) return m;
                    return {
                      ...m,
                      content: m.content + token
                    };
                  })
                );
              },
              onComplete: (res: ChatResponse) => {
                setMessages((prev) =>
                  prev.map((m) => {
                    if (m.id !== assistantMessageId) return m;
                    // Mark all steps completed
                    const steps = (m.executionSteps || []).map((s) => ({
                      ...s,
                      status: 'completed' as const
                    }));
                    return {
                      ...m,
                      content: res.answer || m.content,
                      sources: res.metadata?.sources || res.metadata?.tables_used || [],
                      databaseUsed: res.metadata?.database_used,
                      executionSteps: steps,
                      status: 'complete'
                    };
                  })
                );
                setIsStreaming(false);
                setIsLoading(false);
                setCurrentStep(null);
                abortControllerRef.current = null;
              },
              onError: (err: Error) => {
                markStreamFailed(assistantMessageId, err);
                setIsStreaming(false);
                setIsLoading(false);
                setCurrentStep(null);
                abortControllerRef.current = null;
              }
            },
            abortController.signal
          );
        } catch (err: unknown) {
          if (err instanceof DOMException && err.name === 'AbortError') {
            // User aborted streaming
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMessageId ? { ...m, status: 'complete' } : m
              )
            );
          } else {
            markStreamFailed(
              assistantMessageId,
              err instanceof Error ? err : new Error(String(err))
            );
          }
          setIsStreaming(false);
          setIsLoading(false);
          setCurrentStep(null);
          abortControllerRef.current = null;
        }
      } else {
        // Synchronous fallback
        try {
          const res = await apiServiceRef.current.sendChat(
            trimmed,
            sessionId,
            abortController.signal
          );
          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== assistantMessageId) return m;
              return {
                ...m,
                content: res.answer,
                sources: res.metadata?.sources || res.metadata?.tables_used || [],
                databaseUsed: res.metadata?.database_used,
                status: 'complete'
              };
            })
          );
        } catch (err: unknown) {
          if (err instanceof DOMException && err.name === 'AbortError') {
            // Aborted
          } else {
            const errorMsg = err instanceof Error ? err.message : String(err);
            setError(errorMsg);
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMessageId
                  ? {
                      ...m,
                      status: 'error',
                      content: 'An error occurred while processing your request.'
                    }
                  : m
              )
            );
          }
        } finally {
          setIsLoading(false);
          abortControllerRef.current = null;
        }
      }
    },
    [config.enableStreaming, isLoading, isStreaming, sessionId]
  );

  // Re-ask the question that preceded a failed assistant message
  const retryMessage = useCallback(
    (messageId: string) => {
      const idx = messages.findIndex((m) => m.id === messageId);
      const userMsg = idx > 0 ? messages[idx - 1] : undefined;
      if (!userMsg || userMsg.role !== 'user') return;
      setMessages((prev) => prev.filter((_, i) => i !== idx - 1 && i !== idx));
      void sendMessage(userMsg.content);
    },
    [messages, sendMessage]
  );

  return {
    messages,
    isLoading,
    isStreaming,
    currentStep,
    error,
    sessionId,
    sendMessage,
    stopStreaming,
    clearHistory,
    retryMessage
  };
}
