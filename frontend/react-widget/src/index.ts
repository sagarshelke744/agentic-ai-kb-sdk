/**
 * @agentic-kb/react
 * React SDK for the Agentic AI Database KnowledgeBase Platform
 */

export { AgenticChatbot } from './components/AgenticChatbot';
export type { AgenticChatbotProps } from './components/AgenticChatbot';

export { Header } from './components/Header';
export { ChatWindow } from './components/ChatWindow';
export { Message } from './components/Message';
export { InputBox } from './components/InputBox';
export { SourceBadge } from './components/SourceBadge';
export { ExecutionSteps } from './components/ExecutionSteps';
export { Loading } from './components/Loading';

export { useChat } from './hooks/useChat';
export { ChatApiService } from './services/api';
export type { ChatResponse, StreamCallbacks } from './services/api';

export { DEFAULT_CONFIG } from './config/defaults';
export type { ChatbotConfig, ChatMessage, ExecutionStep } from './config/defaults';

// Style import
import './styles/widget.css';
