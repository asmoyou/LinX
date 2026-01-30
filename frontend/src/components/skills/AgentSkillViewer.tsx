/**
 * Agent Skill Viewer Component
 * Displays agent_skill package files with a file tree on the left and content on the right
 * Similar to Manus interface
 * Supports both view and edit modes
 */

import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X, File, Folder, FolderOpen, ChevronRight, ChevronDown, Loader2, Edit2, Save, Upload } from 'lucide-react';
import { skillsApi, type FileTreeItem } from '@/api/skills';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { ModalPanel } from '@/components/ModalPanel';
import toast from 'react-hot-toast';

interface AgentSkillViewerProps {
  isOpen: boolean;
  onClose: () => void;
  skillId: string;
  skillName: string;
  mode?: 'view' | 'edit';
  onUpdate?: () => void;
}

const AgentSkillViewer: React.FC<AgentSkillViewerProps> = ({
  isOpen,
  onClose,
  skillId,
  skillName,
  mode = 'view',
  onUpdate,
}) => {
  const { t } = useTranslation();
  const [files, setFiles] = useState<FileTreeItem[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>('');
  const [editedContent, setEditedContent] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [contentLoading, setContentLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());
  const [isEditing, setIsEditing] = useState(mode === 'edit');
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);

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
      setEditedContent(data.content);
    } catch (err: any) {
      console.error('Failed to load file content:', err);
      setError(err.response?.data?.detail || err.message || 'Failed to load file content');
      setFileContent('');
      setEditedContent('');
    } finally {
      setContentLoading(false);
    }
  };

  const handleSaveFile = async () => {
    if (!selectedFile) return;
    
    setSaving(true);
    try {
      // TODO: Implement file save API
      await skillsApi.updateFileContent(skillId, selectedFile, editedContent);
      setFileContent(editedContent);
      toast.success(t('skills.fileSaved'));
      if (onUpdate) onUpdate();
    } catch (err: any) {
      console.error('Failed to save file:', err);
      toast.error(err.response?.data?.detail || t('skills.failedToSaveFile'));
    } finally {
      setSaving(false);
    }
  };

  const handleUploadPackage = async () => {
    if (!uploadFile) return;
    
    setSaving(true);
    try {
      const formData = new FormData();
      formData.append('package_file', uploadFile);
      
      await skillsApi.updatePackage(skillId, formData);
      toast.success(t('skills.packageUpdated'));
      setShowUploadDialog(false);
      setUploadFile(null);
      await loadFiles();
      if (onUpdate) onUpdate();
    } catch (err: any) {
      console.error('Failed to upload package:', err);
      toast.error(err.response?.data?.detail || t('skills.failedToUploadPackage'));
    } finally {
      setSaving(false);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const file = e.dataTransfer.files?.[0];
    if (file) {
      // Check file type
      const validTypes = ['.zip', '.tar.gz'];
      const isValid = validTypes.some(type => file.name.toLowerCase().endsWith(type));
      
      if (!isValid) {
        toast.error(t('skills.invalidFileType'));
        return;
      }

      setUploadFile(file);
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" style={{ marginLeft: 'var(--sidebar-width, 0px)' }}>
      <ModalPanel className="w-full max-w-[95vw] h-[90vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between mb-4 pb-4 border-b border-border">
          <div>
            <h2 className="text-xl font-semibold text-foreground">{skillName}</h2>
            <p className="text-sm text-muted-foreground mt-1">
              {isEditing ? t('skills.editAgentSkill') : t('skills.viewAgentSkill')}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {mode === 'edit' && (
              <>
                <button
                  onClick={() => setShowUploadDialog(true)}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-muted hover:bg-muted/80 text-foreground transition-colors"
                >
                  <Upload className="w-4 h-4" />
                  {t('skills.reuploadPackage')}
                </button>
                <button
                  onClick={() => setIsEditing(!isEditing)}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground transition-colors"
                >
                  <Edit2 className="w-4 h-4" />
                  {isEditing ? t('skills.viewMode') : t('skills.editMode')}
                </button>
              </>
            )}
            <button
              onClick={onClose}
              className="p-2 rounded-lg hover:bg-muted/50 transition-colors"
            >
              <X className="w-5 h-5 text-muted-foreground" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 flex gap-4 overflow-hidden">
          {/* Left Sidebar - File Tree */}
          <div className="w-80 border border-border rounded-xl overflow-hidden bg-muted/20 flex flex-col">
            <div className="p-3 border-b border-border bg-muted/30">
              <h3 className="text-sm font-medium text-foreground">
                {t('skills.files')}
              </h3>
            </div>
            <div className="flex-1 overflow-y-auto">
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
          </div>

          {/* Right Content Area */}
          <div className="flex-1 border border-border rounded-xl overflow-hidden flex flex-col bg-background">
            {selectedFile ? (
              <>
                {/* File Header */}
                <div className="px-4 py-3 border-b border-border bg-muted/20 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <File className="w-4 h-4 text-muted-foreground" />
                    <span className="text-sm font-medium text-foreground">
                      {selectedFile}
                    </span>
                  </div>
                  {isEditing && selectedFile && (
                    <button
                      onClick={handleSaveFile}
                      disabled={saving || editedContent === fileContent}
                      className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {saving ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Save className="w-4 h-4" />
                      )}
                      {t('skills.save')}
                    </button>
                  )}
                </div>

                {/* File Content */}
                <div className="flex-1 overflow-auto">
                  {contentLoading ? (
                    <div className="flex items-center justify-center h-full">
                      <Loader2 className="w-8 h-8 animate-spin text-primary" />
                    </div>
                  ) : isEditing ? (
                    <textarea
                      value={editedContent}
                      onChange={(e) => setEditedContent(e.target.value)}
                      className="w-full h-full p-6 bg-transparent text-foreground font-mono text-sm resize-none focus:outline-none"
                      style={{ tabSize: 2 }}
                    />
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

        {/* Upload Dialog */}
        {showUploadDialog && (
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-10">
            <div className="bg-background border border-border rounded-xl p-6 max-w-lg w-full mx-4">
              <h3 className="text-lg font-semibold text-foreground mb-4">
                {t('skills.reuploadPackage')}
              </h3>
              <p className="text-sm text-muted-foreground mb-6">
                {t('skills.reuploadWarning')}
              </p>
              
              {/* Drag and Drop Upload Area */}
              <div 
                className={`border-2 border-dashed rounded-xl p-8 text-center transition-all duration-300 ${
                  isDragging 
                    ? 'border-primary bg-primary/10 scale-[1.02]' 
                    : 'border-border hover:border-primary hover:bg-primary/5'
                }`}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              >
                <input
                  type="file"
                  accept=".zip,.tar.gz"
                  onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                  className="hidden"
                  id="package-reupload"
                />
                <label htmlFor="package-reupload" className="cursor-pointer block">
                  {uploadFile ? (
                    <div className="space-y-3">
                      <div className="w-16 h-16 rounded-full bg-green-500/10 flex items-center justify-center mx-auto">
                        <Upload className="w-8 h-8 text-green-500" />
                      </div>
                      <div>
                        <p className="text-foreground font-semibold mb-1">{uploadFile.name}</p>
                        <p className="text-sm text-muted-foreground">
                          {(uploadFile.size / 1024 / 1024).toFixed(2)} MB
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.preventDefault();
                          setUploadFile(null);
                        }}
                        className="mt-3 px-4 py-2 text-sm text-primary hover:text-primary/80 transition-colors font-medium rounded-lg hover:bg-primary/10"
                      >
                        {t('skills.reselect')}
                      </button>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <div className={`w-16 h-16 rounded-full flex items-center justify-center mx-auto transition-colors ${
                        isDragging ? 'bg-primary/20' : 'bg-muted'
                      }`}>
                        <Upload className={`w-8 h-8 transition-colors ${
                          isDragging ? 'text-primary' : 'text-muted-foreground'
                        }`} />
                      </div>
                      <div>
                        <p className="text-foreground font-semibold mb-1">
                          {t('skills.dragDropOrClick')}
                        </p>
                        <p className="text-sm text-muted-foreground">
                          {t('skills.supportedFormats')}: ZIP, TAR.GZ
                        </p>
                      </div>
                    </div>
                  )}
                </label>
              </div>
              
              <div className="flex gap-2 justify-end mt-6">
                <button
                  onClick={() => {
                    setShowUploadDialog(false);
                    setUploadFile(null);
                    setIsDragging(false);
                  }}
                  className="px-4 py-2 rounded-lg bg-muted hover:bg-muted/80 text-foreground transition-colors"
                >
                  {t('common.cancel')}
                </button>
                <button
                  onClick={handleUploadPackage}
                  disabled={!uploadFile || saving}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {saving ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Upload className="w-4 h-4" />
                  )}
                  {t('skills.upload')}
                </button>
              </div>
            </div>
          </div>
        )}
      </ModalPanel>
    </div>
  );
};

export default AgentSkillViewer;
