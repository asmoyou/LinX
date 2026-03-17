import React from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

interface FileCodePreviewProps {
  filename: string;
  content: string;
}

const LANGUAGE_BY_EXTENSION: Record<string, string> = {
  py: 'python',
  js: 'javascript',
  ts: 'typescript',
  jsx: 'jsx',
  tsx: 'tsx',
  json: 'json',
  yaml: 'yaml',
  yml: 'yaml',
  md: 'markdown',
  txt: 'text',
  sh: 'bash',
  bash: 'bash',
  css: 'css',
  html: 'html',
  xml: 'xml',
  sql: 'sql',
};

function getLanguageFromFilename(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  return LANGUAGE_BY_EXTENSION[ext] || 'text';
}

export const FileCodePreview: React.FC<FileCodePreviewProps> = ({ filename, content }) => {
  return (
    <SyntaxHighlighter
      language={getLanguageFromFilename(filename)}
      style={vscDarkPlus}
      customStyle={{
        height: '100%',
        margin: 0,
        overflow: 'auto',
        padding: '1.5rem',
        background: 'transparent',
        fontSize: '0.875rem',
        lineHeight: '1.5',
      }}
      showLineNumbers
    >
      {content}
    </SyntaxHighlighter>
  );
};
