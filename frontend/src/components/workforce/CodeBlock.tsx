/**
 * CodeBlock Component - Syntax highlighted code blocks
 *
 * Renders code blocks with syntax highlighting using react-syntax-highlighter.
 * Supports multiple languages, line numbers, and copy-to-clipboard.
 */

import React, { useState } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Copy, Check } from 'lucide-react';

interface CodeBlockProps {
  language?: string;
  children: string;
  inline?: boolean;
}

export const CodeBlock: React.FC<CodeBlockProps> = ({
  language = 'text',
  children,
  inline = false
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(children);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  // For inline code, use simple styling
  if (inline) {
    return (
      <code className="px-1.5 py-0.5 rounded bg-zinc-200 dark:bg-zinc-700 text-pink-600 dark:text-pink-400 text-sm font-mono">
        {children}
      </code>
    );
  }

  // Normalize language names
  const normalizedLanguage = language?.toLowerCase() || 'text';
  const langMap: Record<string, string> = {
    'sh': 'bash',
    'shell': 'bash',
    'zsh': 'bash',
    'js': 'javascript',
    'ts': 'typescript',
    'py': 'python',
    'yml': 'yaml',
  };
  const finalLanguage = langMap[normalizedLanguage] || normalizedLanguage;

  return (
    <div className="relative group rounded-lg overflow-hidden my-3">
      {/* Header with language label and copy button */}
      <div className="flex items-center justify-between px-4 py-2 bg-zinc-800 dark:bg-zinc-900 border-b border-zinc-700">
        <span className="text-xs font-medium text-zinc-400 uppercase tracking-wide">
          {finalLanguage}
        </span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 px-2 py-1 text-xs text-zinc-400 hover:text-white hover:bg-zinc-700 rounded transition-colors"
          title="Copy code"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-green-400" />
              <span className="text-green-400">Copied!</span>
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>

      {/* Code content with syntax highlighting */}
      <div className="overflow-x-auto">
        <SyntaxHighlighter
          language={finalLanguage}
          style={oneDark}
          customStyle={{
            margin: 0,
            padding: '1rem',
            fontSize: '0.85rem',
            lineHeight: '1.5',
            backgroundColor: '#1e1e1e',
            borderRadius: 0,
          }}
          showLineNumbers={children.split('\n').length > 3}
          lineNumberStyle={{
            minWidth: '2.5em',
            paddingRight: '1em',
            color: '#6b7280',
            userSelect: 'none',
          }}
          wrapLines={true}
          wrapLongLines={false}
        >
          {children.trim()}
        </SyntaxHighlighter>
      </div>
    </div>
  );
};

/**
 * Creates components object for ReactMarkdown to use CodeBlock
 */
export const createMarkdownComponents = () => ({
  code({ node, inline, className, children, ...props }: any) {
    const match = /language-(\w+)/.exec(className || '');
    const codeString = String(children).replace(/\n$/, '');

    // Check if it's inline code (no language and short)
    if (inline || (!match && codeString.length < 100 && !codeString.includes('\n'))) {
      return (
        <code className="px-1.5 py-0.5 rounded bg-zinc-200 dark:bg-zinc-700 text-pink-600 dark:text-pink-400 text-sm font-mono" {...props}>
          {children}
        </code>
      );
    }

    return (
      <CodeBlock language={match ? match[1] : 'text'}>
        {codeString}
      </CodeBlock>
    );
  },
  // Override pre to prevent double wrapping
  pre({ children }: any) {
    return <>{children}</>;
  },
});
