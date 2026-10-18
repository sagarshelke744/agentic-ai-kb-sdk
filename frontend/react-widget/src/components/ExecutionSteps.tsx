import React, { useState } from 'react';
import { ChevronDown, ChevronRight, CheckCircle2, CircleDashed, XCircle, AlertTriangle } from 'lucide-react';
import { ExecutionStep } from '../config/defaults';

export interface ExecutionStepsProps {
  steps?: ExecutionStep[];
  isStreaming?: boolean;
}

export const ExecutionSteps: React.FC<ExecutionStepsProps> = ({ steps, isStreaming }) => {
  const [isOpen, setIsOpen] = useState<boolean>(Boolean(isStreaming));

  if (!steps || steps.length === 0) return null;

  const activeStep = steps.find((s) => s.status === 'running') || steps[steps.length - 1];

  return (
    <div className="akb-steps-container">
      <button
        type="button"
        className="akb-steps-toggle"
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {isStreaming ? (
            <span className="akb-spinner" style={{ width: 12, height: 12 }} />
          ) : steps.some((st) => st.status === 'failed') ? (
            <XCircle size={13} color="var(--akb-accent-rose)" />
          ) : (
            <CheckCircle2 size={13} color="var(--akb-accent-emerald)" />
          )}
          <span>
            {isStreaming && activeStep ? activeStep.name : `${steps.length} reasoning steps`}
          </span>
        </span>
        {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>

      {isOpen && (
        <div className="akb-steps-list">
          {steps.map((step) => {
            const isRunning = step.status === 'running';
            const isCompleted = step.status === 'completed';
            const isFailed = step.status === 'failed';
            const isWarning = step.status === 'warning';

            return (
              <div
                key={step.id}
                className={`akb-step-item ${isRunning ? 'akb-step-running' : ''} ${
                  isCompleted ? 'akb-step-completed' : ''
                } ${isFailed ? 'akb-step-failed' : ''} ${isWarning ? 'akb-step-warning' : ''}`}
              >
                {isRunning ? (
                  <span className="akb-spinner" style={{ width: 11, height: 11 }} />
                ) : isFailed ? (
                  <XCircle size={13} />
                ) : isWarning ? (
                  <AlertTriangle size={13} />
                ) : isCompleted ? (
                  <CheckCircle2 size={13} />
                ) : (
                  <CircleDashed size={13} />
                )}
                <span>{step.name}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
