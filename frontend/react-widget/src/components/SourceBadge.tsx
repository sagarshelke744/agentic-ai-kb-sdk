import React from 'react';
import { Database } from 'lucide-react';

export interface SourceBadgeProps {
  sources?: string[];
  databaseUsed?: boolean;
}

export const SourceBadge: React.FC<SourceBadgeProps> = ({ sources, databaseUsed }) => {
  if (!sources || sources.length === 0) {
    if (databaseUsed) {
      return (
        <div className="akb-sources-row">
          <span className="akb-sources-label">Source:</span>
          <span className="akb-source-chip">
            <Database size={12} />
            <span>Database Query</span>
          </span>
        </div>
      );
    }
    return null;
  }

  return (
    <div className="akb-sources-row">
      <span className="akb-sources-label">Sources:</span>
      {sources.map((source, index) => (
        <span key={`${source}-${index}`} className="akb-source-chip" title={`Grounded from ${source}`}>
          <Database size={12} />
          <span>{source}</span>
        </span>
      ))}
    </div>
  );
};
