import React, { useState } from 'react';
import { X } from 'lucide-react';
import { GlassPanel } from '@/components/GlassPanel';

interface AddAgentModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAdd: (name: string, template: string) => void;
}

const templates = [
  { id: 'data-analyst', name: 'Data Analyst', description: 'Analyze data and generate insights' },
  { id: 'content-writer', name: 'Content Writer', description: 'Create and edit content' },
  { id: 'code-assistant', name: 'Code Assistant', description: 'Help with coding tasks' },
  { id: 'research-assistant', name: 'Research Assistant', description: 'Research and summarize information' },
];

export const AddAgentModal: React.FC<AddAgentModalProps> = ({ isOpen, onClose, onAdd }) => {
  const [name, setName] = useState('');
  const [selectedTemplate, setSelectedTemplate] = useState('');

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (name && selectedTemplate) {
      onAdd(name, selectedTemplate);
      setName('');
      setSelectedTemplate('');
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <GlassPanel className="w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-gray-800 dark:text-white">Add New Agent</h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/20 rounded-lg transition-colors"
          >
            <X className="w-6 h-6 text-gray-700 dark:text-gray-300" />
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          {/* Agent Name */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Agent Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Data Analyst #1"
              className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-gray-800 dark:text-white placeholder-gray-500"
              required
            />
          </div>

          {/* Template Selection */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Select Template
            </label>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {templates.map((template) => (
                <button
                  key={template.id}
                  type="button"
                  onClick={() => setSelectedTemplate(template.id)}
                  className={`p-4 rounded-lg border-2 transition-all text-left ${
                    selectedTemplate === template.id
                      ? 'border-indigo-500 bg-indigo-500/10'
                      : 'border-white/20 hover:border-white/40'
                  }`}
                >
                  <h3 className="font-semibold text-gray-800 dark:text-white mb-1">
                    {template.name}
                  </h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    {template.description}
                  </p>
                </button>
              ))}
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={!name || !selectedTemplate}
              className="flex-1 px-4 py-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium"
            >
              Create Agent
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-white/10 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-white/20 transition-colors font-medium"
            >
              Cancel
            </button>
          </div>
        </form>
      </GlassPanel>
    </div>
  );
};
