/**
 * Embeddable Standalone JavaScript Widget Entry Point (Phase 9)
 * Exposes window.AgenticKB.init({...}) for seamless embedding into any HTML page,
 * Vue, Angular, or legacy enterprise application.
 */

import React from 'react';
import { createRoot, Root } from 'react-dom/client';
import { AgenticChatbot } from './components/AgenticChatbot';
import { ChatbotConfig } from './config/defaults';
import './styles/widget.css';

export interface WidgetInstance {
  destroy: () => void;
  update: (newConfig: Partial<ChatbotConfig>) => void;
}

export interface AgenticKBGlobal {
  version: string;
  init: (options?: Partial<ChatbotConfig>) => WidgetInstance;
}

declare global {
  interface Window {
    AgenticKB?: AgenticKBGlobal;
  }
}

let activeRoot: Root | null = null;
let activeContainer: HTMLElement | null = null;

export function init(options: Partial<ChatbotConfig> = {}): WidgetInstance {
  // If already initialized, clean up previous instance
  if (activeRoot && activeContainer) {
    try {
      activeRoot.unmount();
      activeContainer.remove();
    } catch {
      // ignore
    }
    activeRoot = null;
    activeContainer = null;
  }

  // Create isolated mount container
  const container = document.createElement('div');
  container.id = 'agentic-kb-widget-container';
  document.body.appendChild(container);
  activeContainer = container;

  const root = createRoot(container);
  activeRoot = root;

  let currentConfig: Partial<ChatbotConfig> = { ...options };

  const render = () => {
    root.render(React.createElement(AgenticChatbot, currentConfig));
  };

  render();

  const instance: WidgetInstance = {
    destroy: () => {
      if (activeRoot) {
        activeRoot.unmount();
        activeRoot = null;
      }
      if (activeContainer && activeContainer.parentNode) {
        activeContainer.parentNode.removeChild(activeContainer);
        activeContainer = null;
      }
    },
    update: (newConfig: Partial<ChatbotConfig>) => {
      currentConfig = { ...currentConfig, ...newConfig };
      render();
    }
  };

  return instance;
}

export const AgenticKB: AgenticKBGlobal = {
  version: '0.1.0',
  init
};

// Attach to window object for global script tag usage
if (typeof window !== 'undefined') {
  window.AgenticKB = AgenticKB;

  // Auto-init via data attributes on the current script tag if present
  // e.g. <script src="agentic-kb-widget.js" data-api-url="http://localhost:8000" data-auto-init></script>
  const currentScript = document.currentScript as HTMLScriptElement | null;
  if (currentScript && (currentScript.hasAttribute('data-auto-init') || currentScript.getAttribute('data-api-url'))) {
    const apiUrl = currentScript.getAttribute('data-api-url') || 'http://localhost:8000';
    const assistantName = currentScript.getAttribute('data-assistant-name') || undefined;
    const theme = (currentScript.getAttribute('data-theme') as 'dark' | 'light') || undefined;
    const position = (currentScript.getAttribute('data-position') as 'bottom-right' | 'bottom-left') || undefined;

    window.addEventListener('DOMContentLoaded', () => {
      init({ apiUrl, assistantName, theme, position });
    });
  }
}

export default AgenticKB;
