/**
 * Custom React Hook for Managing Agentic Chat State, Streaming, and History
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { ChatbotConfig, ChatMessage, ExecutionStep, DEFAULT_CONFIG } from '../config/defaults';
import { ChatApiService, ChatResponse } from '../services/api';

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
                      sources: res.metadata?.tables_used || [],
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
                setError(err.message);
                setMessages((prev) =>
                  prev.map((m) => {
                    if (m.id !== assistantMessageId) return m;
                    return {
                      ...m,
                      status: 'error',
                      content:
                        m.content ||
                        'I encountered an error retrieving data from the knowledgebase. Please check your query or try again.'
                    };
                  })
                );
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
            const errorMsg = err instanceof Error ? err.message : String(err);
            setError(errorMsg);
            setMessages((prev) =>
              prev.map((m) => {
                if (m.id !== assistantMessageId) return m;
                return {
                  ...m,
                  status: 'error',
                  content:
                    m.content ||
                    'I encountered an error connecting to the service. Please verify your connection or try again.'
                };
              })
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
                sources: res.metadata?.tables_used || [],
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

  return {
    messages,
    isLoading,
    isStreaming,
    currentStep,
    error,
    sessionId,
    sendMessage,
    stopStreaming,
    clearHistory
  };
}
