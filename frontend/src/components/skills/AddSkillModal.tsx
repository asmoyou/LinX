import { X, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import type { CreateSkillRequest } from '@/api/skills';

interface AddSkillModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: CreateSkillRequest) => Promise<void>;
}

export default function AddSkillModal({ isOpen, onClose, onSubmit }: AddSkillModalProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formData, setFormData] = useState<CreateSkillRequest>({
    name: '',
    description: '',
    interface_definition: {
      inputs: {},
      outputs: {},
      required_inputs: [],
    },
    dependencies: [],
    version: '1.0.0',
  });

  const [newInput, setNewInput] = useState({ key: '', type: 'string' });
  const [newOutput, setNewOutput] = useState({ key: '', type: 'string' });
  const [newDependency, setNewDependency] = useState('');

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await onSubmit(formData);
      handleClose();
    } catch (error) {
      console.error('Failed to create skill:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    setFormData({
      name: '',
      description: '',
      interface_definition: {
        inputs: {},
        outputs: {},
        required_inputs: [],
      },
      dependencies: [],
      version: '1.0.0',
    });
    setNewInput({ key: '', type: 'string' });
    setNewOutput({ key: '', type: 'string' });
    setNewDependency('');
    onClose();
  };

  const addInput = () => {
    if (newInput.key.trim()) {
      setFormData({
        ...formData,
        interface_definition: {
          ...formData.interface_definition,
          inputs: {
            ...formData.interface_definition.inputs,
            [newInput.key]: newInput.type,
          },
        },
      });
      setNewInput({ key: '', type: 'string' });
    }
  };

  const removeInput = (key: string) => {
    const { [key]: _, ...rest } = formData.interface_definition.inputs;
    setFormData({
      ...formData,
      interface_definition: {
        ...formData.interface_definition,
        inputs: rest,
      },
    });
  };

  const addOutput = () => {
    if (newOutput.key.trim()) {
      setFormData({
        ...formData,
        interface_definition: {
          ...formData.interface_definition,
          outputs: {
            ...formData.interface_definition.outputs,
            [newOutput.key]: newOutput.type,
          },
        },
      });
      setNewOutput({ key: '', type: 'string' });
    }
  };

  const removeOutput = (key: string) => {
    const { [key]: _, ...rest } = formData.interface_definition.outputs;
    setFormData({
      ...formData,
      interface_definition: {
        ...formData.interface_definition,
        outputs: rest,
      },
    });
  };

  const addDependency = () => {
    if (newDependency.trim() && !formData.dependencies?.includes(newDependency)) {
      setFormData({
        ...formData,
        dependencies: [...(formData.dependencies || []), newDependency],
      });
      setNewDependency('');
    }
  };

  const removeDependency = (dep: string) => {
    setFormData({
      ...formData,
      dependencies: formData.dependencies?.filter((d) => d !== dep) || [],
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="glass-panel w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-border/50">
          <h2 className="text-xl font-semibold text-foreground">Add New Skill</h2>
          <button
            onClick={handleClose}
            className="p-2 rounded-lg hover:bg-muted/50 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          {/* Basic Info */}
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-foreground mb-2">
                Skill Name *
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="w-full px-4 py-2 rounded-lg bg-muted/50 border border-border/50 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                placeholder="e.g., web_search, data_analysis"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground mb-2">
                Description *
              </label>
              <textarea
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="w-full px-4 py-2 rounded-lg bg-muted/50 border border-border/50 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 resize-none"
                placeholder="Describe what this skill does..."
                rows={3}
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground mb-2">
                Version
              </label>
              <input
                type="text"
                value={formData.version}
                onChange={(e) => setFormData({ ...formData, version: e.target.value })}
                className="w-full px-4 py-2 rounded-lg bg-muted/50 border border-border/50 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                placeholder="1.0.0"
              />
            </div>
          </div>

          {/* Inputs */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              Input Parameters
            </label>
            <div className="space-y-2">
              {Object.entries(formData.interface_definition.inputs).map(([key, type]) => (
                <div key={key} className="flex items-center gap-2">
                  <input
                    type="text"
                    value={key}
                    disabled
                    className="flex-1 px-3 py-2 rounded-lg bg-muted/30 border border-border/50 text-foreground text-sm"
                  />
                  <input
                    type="text"
                    value={type}
                    disabled
                    className="w-32 px-3 py-2 rounded-lg bg-muted/30 border border-border/50 text-foreground text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => removeInput(key)}
                    className="p-2 rounded-lg hover:bg-destructive/10 text-destructive transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={newInput.key}
                  onChange={(e) => setNewInput({ ...newInput, key: e.target.value })}
                  className="flex-1 px-3 py-2 rounded-lg bg-muted/50 border border-border/50 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 text-sm"
                  placeholder="Parameter name"
                />
                <select
                  value={newInput.type}
                  onChange={(e) => setNewInput({ ...newInput, type: e.target.value })}
                  className="w-32 px-3 py-2 rounded-lg bg-muted/50 border border-border/50 text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 text-sm"
                >
                  <option value="string">string</option>
                  <option value="integer">integer</option>
                  <option value="float">float</option>
                  <option value="boolean">boolean</option>
                  <option value="array">array</option>
                  <option value="dict">dict</option>
                  <option value="any">any</option>
                </select>
                <button
                  type="button"
                  onClick={addInput}
                  className="p-2 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary transition-colors"
                >
                  <Plus className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>

          {/* Outputs */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              Output Parameters
            </label>
            <div className="space-y-2">
              {Object.entries(formData.interface_definition.outputs).map(([key, type]) => (
                <div key={key} className="flex items-center gap-2">
                  <input
                    type="text"
                    value={key}
                    disabled
                    className="flex-1 px-3 py-2 rounded-lg bg-muted/30 border border-border/50 text-foreground text-sm"
                  />
                  <input
                    type="text"
                    value={type}
                    disabled
                    className="w-32 px-3 py-2 rounded-lg bg-muted/30 border border-border/50 text-foreground text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => removeOutput(key)}
                    className="p-2 rounded-lg hover:bg-destructive/10 text-destructive transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={newOutput.key}
                  onChange={(e) => setNewOutput({ ...newOutput, key: e.target.value })}
                  className="flex-1 px-3 py-2 rounded-lg bg-muted/50 border border-border/50 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 text-sm"
                  placeholder="Parameter name"
                />
                <select
                  value={newOutput.type}
                  onChange={(e) => setNewOutput({ ...newOutput, type: e.target.value })}
                  className="w-32 px-3 py-2 rounded-lg bg-muted/50 border border-border/50 text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 text-sm"
                >
                  <option value="string">string</option>
                  <option value="integer">integer</option>
                  <option value="float">float</option>
                  <option value="boolean">boolean</option>
                  <option value="array">array</option>
                  <option value="dict">dict</option>
                  <option value="any">any</option>
                </select>
                <button
                  type="button"
                  onClick={addOutput}
                  className="p-2 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary transition-colors"
                >
                  <Plus className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>

          {/* Dependencies */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              Dependencies
            </label>
            <div className="space-y-2">
              {formData.dependencies && formData.dependencies.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {formData.dependencies.map((dep) => (
                    <div
                      key={dep}
                      className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-muted/50 border border-border/50"
                    >
                      <span className="text-sm text-foreground font-mono">{dep}</span>
                      <button
                        type="button"
                        onClick={() => removeDependency(dep)}
                        className="text-muted-foreground hover:text-destructive transition-colors"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={newDependency}
                  onChange={(e) => setNewDependency(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), addDependency())}
                  className="flex-1 px-3 py-2 rounded-lg bg-muted/50 border border-border/50 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 text-sm"
                  placeholder="e.g., requests, pandas, beautifulsoup4"
                />
                <button
                  type="button"
                  onClick={addDependency}
                  className="p-2 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary transition-colors"
                >
                  <Plus className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end gap-3 pt-4 border-t border-border/50">
            <button
              type="button"
              onClick={handleClose}
              className="px-4 py-2 rounded-lg bg-muted/50 hover:bg-muted text-foreground transition-colors"
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={isSubmitting}
            >
              {isSubmitting ? 'Creating...' : 'Create Skill'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
