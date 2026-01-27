import React, { ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import ErrorBoundary from './ErrorBoundary';

interface PageErrorBoundaryProps {
  children: ReactNode;
  pageName?: string;
}

/**
 * Page-level Error Boundary
 * Provides a lighter error UI for page-specific errors
 */
export default function PageErrorBoundary({ children, pageName }: PageErrorBoundaryProps) {
  const fallback = (
    <div className="flex items-center justify-center min-h-[400px] p-8">
      <div className="text-center max-w-md">
        <div className="flex justify-center mb-4">
          <div className="p-3 rounded-full bg-red-500/10">
            <AlertTriangle className="w-12 h-12 text-red-400" />
          </div>
        </div>
        <h2 className="text-xl font-semibold text-foreground mb-2">
          {pageName ? `${pageName}加载失败` : '页面加载失败'}
        </h2>
        <p className="text-sm text-muted-foreground mb-4">
          页面遇到了一个错误，请尝试刷新页面
        </p>
        <button
          onClick={() => window.location.reload()}
          className="px-4 py-2 rounded-xl bg-primary hover:bg-primary/90 text-white font-medium transition-colors inline-flex items-center gap-2"
        >
          <RefreshCw className="w-4 h-4" />
          刷新页面
        </button>
      </div>
    </div>
  );

  return <ErrorBoundary fallback={fallback}>{children}</ErrorBoundary>;
}
