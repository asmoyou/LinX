import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

/**
 * Global Error Boundary Component
 * Catches JavaScript errors anywhere in the child component tree
 */
class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: Error): State {
    // Update state so the next render will show the fallback UI
    return {
      hasError: true,
      error,
      errorInfo: null,
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Log error to console in development
    console.error('ErrorBoundary caught an error:', error, errorInfo);

    // Update state with error details
    this.setState({
      error,
      errorInfo,
    });

    // Call custom error handler if provided
    if (this.props.onError) {
      this.props.onError(error, errorInfo);
    }

    // TODO: Send error to logging service (e.g., Sentry, LogRocket)
    // logErrorToService(error, errorInfo);
  }

  handleReset = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });
  };

  handleReload = () => {
    window.location.reload();
  };

  handleGoHome = () => {
    window.location.href = '/';
  };

  render() {
    if (this.state.hasError) {
      // Custom fallback UI if provided
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // Default error UI
      return (
        <div className="min-h-screen flex items-center justify-center bg-background p-4">
          <div className="max-w-2xl w-full">
            <div className="glass-panel rounded-2xl p-8 text-center">
              {/* Error Icon */}
              <div className="flex justify-center mb-6">
                <div className="p-4 rounded-full bg-red-500/10">
                  <AlertTriangle className="w-16 h-16 text-red-400" />
                </div>
              </div>

              {/* Error Title */}
              <h1 className="text-3xl font-bold text-foreground mb-4">
                页面出错了
              </h1>

              {/* Error Description */}
              <p className="text-muted-foreground mb-6">
                抱歉，页面遇到了一个错误。我们已经记录了这个问题，会尽快修复。
              </p>

              {/* Error Details (Development Only) */}
              {import.meta.env.DEV && this.state.error && (
                <div className="mb-6 text-left">
                  <details className="bg-muted/50 rounded-xl p-4">
                    <summary className="cursor-pointer text-sm font-medium text-foreground mb-2">
                      错误详情（开发模式）
                    </summary>
                    <div className="mt-2 space-y-2">
                      <div>
                        <p className="text-xs font-semibold text-red-400 mb-1">错误信息：</p>
                        <pre className="text-xs text-muted-foreground bg-background/50 p-2 rounded overflow-x-auto">
                          {this.state.error.toString()}
                        </pre>
                      </div>
                      {this.state.errorInfo && (
                        <div>
                          <p className="text-xs font-semibold text-red-400 mb-1">组件堆栈：</p>
                          <pre className="text-xs text-muted-foreground bg-background/50 p-2 rounded overflow-x-auto max-h-48 overflow-y-auto">
                            {this.state.errorInfo.componentStack}
                          </pre>
                        </div>
                      )}
                    </div>
                  </details>
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex flex-col sm:flex-row gap-3 justify-center">
                <button
                  onClick={this.handleReset}
                  className="px-6 py-3 rounded-xl bg-primary hover:bg-primary/90 text-white font-medium transition-colors flex items-center justify-center gap-2"
                >
                  <RefreshCw className="w-4 h-4" />
                  重试
                </button>
                <button
                  onClick={this.handleReload}
                  className="px-6 py-3 rounded-xl bg-muted hover:bg-muted/80 text-foreground font-medium transition-colors flex items-center justify-center gap-2"
                >
                  <RefreshCw className="w-4 h-4" />
                  刷新页面
                </button>
                <button
                  onClick={this.handleGoHome}
                  className="px-6 py-3 rounded-xl bg-muted hover:bg-muted/80 text-foreground font-medium transition-colors flex items-center justify-center gap-2"
                >
                  <Home className="w-4 h-4" />
                  返回首页
                </button>
              </div>

              {/* Help Text */}
              <p className="text-xs text-muted-foreground mt-6">
                如果问题持续存在，请联系技术支持或查看控制台获取更多信息
              </p>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
