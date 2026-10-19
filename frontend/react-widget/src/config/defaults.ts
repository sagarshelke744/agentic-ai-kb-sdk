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
  assistantName: 'Sagar DB Assistant',
  assistantSubtitle: 'SQL Server · 4 Enterprise Tables',
  welcomeMessage: 'Hello! I can answer questions across your employee, department, project, and sales order tables in the Sagar database. Try asking me anything!',
  theme: 'dark',
  position: 'bottom-right',
  showSources: true,
  showExecutionSteps: true,
  enableStreaming: true,
  suggestedPrompts: [
    'Who earns the highest salary?',
    'Which department has the highest budget?',
    'Show all projects currently in progress',
    'What is our total revenue from orders?',
    'Which orders were shipped or delivered to Mumbai?',
    'List all department managers and locations',
  ],
  isFloating: true,
  isOpenDefault: true,
  persistSession: true
};
