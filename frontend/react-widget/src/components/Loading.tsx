import React from 'react';

export interface LoadingProps {
  currentStep?: string | null;
}

export const Loading: React.FC<LoadingProps> = ({ currentStep }) => {
  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}>
      <div className="akb-typing-indicator">
        <span className="akb-typing-dot" />
        <span className="akb-typing-dot" />
        <span className="akb-typing-dot" />
      </div>
      {currentStep && (
        <span style={{ fontSize: 12, color: 'var(--akb-text-secondary)', display: 'flex', alignItems: 'center', gap: 6 }}>
          <span className="akb-spinner" style={{ width: 10, height: 10 }} />
          <span>{currentStep}</span>
        </span>
      )}
    </div>
  );
};
