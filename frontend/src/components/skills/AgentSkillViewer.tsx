/**
 * Agent Skill Viewer Component
 * Displays agent_skill package files with a file tree on the left and content on the right
 * Similar to Manus interface
 */

import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X, File, Folder, FolderOpen, ChevronRight, ChevronDown, Loader2 } from 'lucide-react';
import { skillsApi, type FileTreeItem } from '@/api/skills';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

interface AgentSkillViewerProps {
  isOpen: boolean;
  onClose: () => void;
  skillId: string;
  skillName: string;
}

const AgentSkillViewer: React.FC<AgentSkillViewerProps> = ({
  isOpen,
  onClose,
  skillId,
  skillName,
}) => {
  const { t } = useTranslation();
  const [files, setFiles] = useState<FileTreeItem[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [contentLoading, setContentLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());

  // Load file list when modal opens
  useEffect(() => {
    if (isOpen && skillId) {
      loadFiles();
    }
  }, [isOpen, skillId]);

  const loadFiles = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await skillsApi.getFiles(skillId);
      setFiles(data.files);
      
      // Auto-select SKILL.md if it exists
      const skillMd = findFile(data.files, 'SKILL.md');
      if (skillMd) {
        handleFileSelect(skillMd.path);
      }
    } catch (err: any) {
      console.error('Failed to load files:', err);
      setError(err.response?.data?.message || 'Failed to load files');
    } finally {
      setLoading(false);
    }
  };

  const findFile = (items: FileTreeItem[], name: string): FileTreeItem | null => {
    for (const item of items) {
      if (item.type === 'file' && item.name === name) {
        return item;
      }
      if (item.type === 'directory' && item.children) {
        const found = findFile(item.children, name);
        if (found) return found;
      }
    }
    return null;
  };

  const handleFileSelect = async (filePath: string) => {
    setSelectedFile(filePath);
    setContentLoading(true);
    setError(null);
    
    try {
      const data = await skillsApi.getFileContent(skillId, filePath);
      setFileContent(data.content);
    } catch (err: any) {
      console.error('Failed to load file content:', err);
      setError(err.response?.data?.message || 'Failed to load file content');
      setFileContent('');
    } finally {
      setContentLoading(false);
    }
  };

  const toggleFolder = (path: string) => {
    const newExpanded = new Set(expandedFolders);
    if (newExpanded.has(path)) {
      newExpanded.delete(path);
    } else {
      newExpanded.add(path);
    }
    setExpandedFolders(newExpanded);
  };

  const getLanguageFromExtension = (filename: string): string => {
    const ext = filename.split('.').pop()?.toLowerCase();
    const languageMap: Record<string, string> = {
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
    return languageMap[ext || ''] || 'text';
  };

  const renderFileTree = (items: FileTreeItem[], level = 0) => {
    return items.map((item) => {
      const isExpanded = expandedFolders.has(item.path);
      const isSelected = selectedFile === item.path;

      if (item.type === 'directory') {
        return (
          <div key={item.path}>
            <div
              className={`flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-muted/50 transition-colors ${
                level > 0 ? `ml-${level * 4}` : ''
              }`}
              style={{ paddingLeft: `${level * 16 + 12}px` }}
              onClick={() => toggleFolder(item.path)}
            >
              {isExpanded ? (
                <ChevronDown className="w-4 h-4 text-muted-foreground" />
              ) : (
                <ChevronRight className="w-4 h-4 text-muted-foreground" />
              )}
              {isExpanded ? (
                <FolderOpen className="w-4 h-4 text-blue-400" />
              ) : (
                <Folder className="w-4 h-4 text-blue-400" />
              )}
              <span className="text-sm text-foreground">{item.name}</span>
            </div>
            {isExpanded && item.children && (
              <div>{renderFileTree(item.children, level + 1)}</div>
            )}
          </div>
        );
      }

      return (
        <div
          key={item.path}
          className={`flex items-center gap-2 px-3 py-2 cursor-pointer transition-colors ${
            isSelected ? 'bg-primary/20 text-primary' : 'hover:bg-muted/50 text-foreground'
          }`}
          style={{ paddingLeft: `${level * 16 + 28}px` }}
          onClick={() => handleFileSelect(item.path)}
        >
          <File className="w-4 h-4" />
          <span className="text-sm">{item.name}</span>
          {item.size !== undefined && (
            <span className="text-xs text-muted-foreground ml-auto">
              {formatFileSize(item.size)}
            </span>
          )}
        </div>
      );
    });
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-background border border-border rounded-2xl shadow-2xl w-[95vw] h-[90vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div>
            <h2 className="text-xl font-semibold text-foreground">{skillName}</h2>
            <p className="text-sm text-muted-foreground mt-1">
              {t('skills.agentSkillPackageViewer')}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-muted/50 transition-colors"
          >
            <X className="w-5 h-5 text-muted-foreground" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left Sidebar - File Tree */}
          <div className="w-80 border-r border-border overflow-y-auto bg-muted/20">
            <div className="p-3 border-b border-border">
              <h3 className="text-sm font-medium text-foreground">
                {t('skills.files')}
              </h3>
            </div>
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-6 h-6 animate-spin text-primary" />
              </div>
            ) : error ? (
              <div className="p-4 text-sm text-destructive">{error}</div>
            ) : (
              <div className="py-2">{renderFileTree(files)}</div>
            )}
          </div>

          {/* Right Content Area */}
          <div className="flex-1 overflow-hidden flex flex-col">
            {selectedFile ? (
              <>
                {/* File Header */}
                <div className="px-6 py-3 border-b border-border bg-muted/20">
                  <div className="flex items-center gap-2">
                    <File className="w-4 h-4 text-muted-foreground" />
                    <span className="text-sm font-medium text-foreground">
                      {selectedFile}
                    </span>
                  </div>
                </div>

                {/* File Content */}
                <div className="flex-1 overflow-auto">
                  {contentLoading ? (
                    <div className="flex items-center justify-center h-full">
                      <Loader2 className="w-8 h-8 animate-spin text-primary" />
                    </div>
                  ) : (
                    <SyntaxHighlighter
                      language={getLanguageFromExtension(selectedFile)}
                      style={vscDarkPlus}
                      customStyle={{
                        margin: 0,
                        padding: '1.5rem',
                        background: 'transparent',
                        fontSize: '0.875rem',
                        lineHeight: '1.5',
                      }}
                      showLineNumbers
                    >
                      {fileContent}
                    </SyntaxHighlighter>
                  )}
                </div>
              </>
            ) : (
              <div className="flex items-center justify-center h-full text-muted-foreground">
                <div className="text-center">
                  <File className="w-16 h-16 mx-auto mb-4 opacity-50" />
                  <p className="text-sm">{t('skills.selectFileToView')}</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default AgentSkillViewer;
