/**
 * Configuration and Defaults for Agentic KnowledgeBase Chatbot Widget
 */

export interface ExecutionStep {
  id: string;
  name: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'warning';
  details?: string;
  timestamp: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  sources?: string[];
  executionSteps?: ExecutionStep[];
  status?: 'streaming' | 'complete' | 'error';
  databaseUsed?: boolean;
  error?: { message: string; code?: string; retryable?: boolean };
}

export interface ChatbotConfig {
  apiUrl: string;
  apiKey?: string;
  tenantId?: string;
  userId?: string;
  assistantName?: string;
  assistantSubtitle?: string;
  welcomeMessage?: string;
  theme?: 'dark' | 'light' | 'auto';
  position?: 'bottom-right' | 'bottom-left' | 'top-right' | 'top-left';
  showSources?: boolean;
  showExecutionSteps?: boolean;
  enableStreaming?: boolean;
  suggestedPrompts?: string[];
  primaryColor?: string;
  isFloating?: boolean;
  isOpenDefault?: boolean;
  persistSession?: boolean;
}

export const DEFAULT_CONFIG: Required<Omit<ChatbotConfig, 'apiKey' | 'tenantId' | 'userId' | 'primaryColor'>> = {
  apiUrl: 'http://localhost:8000',
  assistantName: 'Data Intelligence Assistant',
  assistantSubtitle: 'Grounded in Enterprise KnowledgeBase',
  welcomeMessage: 'Hello! I am your enterprise database assistant. You can ask me natural language questions about your business metrics, transactions, and data.',
  theme: 'dark',
  position: 'bottom-right',
  showSources: true,
  showExecutionSteps: true,
  enableStreaming: true,
  suggestedPrompts: [
    'What were our total sales last month?',
    'Show top 5 customers by revenue',
    'Which products had zero orders in Q3?',
    'Explain the structure of orders and customers'
  ],
  isFloating: true,
  isOpenDefault: false,
  persistSession: true
};
