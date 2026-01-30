import { useState, useEffect } from 'react';
import { Plus, Search, RefreshCw, Package, Layers } from 'lucide-react';
import SkillCardV2 from '@/components/skills/SkillCardV2';
import AddSkillModalV2 from '@/components/skills/AddSkillModalV2';
import EditSkillModal from '@/components/skills/EditSkillModal';
import CodePreviewModal from '@/components/skills/CodePreviewModal';
import AgentSkillViewer from '@/components/skills/AgentSkillViewer';
import SkillTesterModal from '@/components/skills/SkillTesterModal';
import { skillsApi, type Skill, type CreateSkillRequest } from '@/api/skills';
import { useTranslation } from 'react-i18next';

export default function Skills() {
  const { t } = useTranslation();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [filteredSkills, setFilteredSkills] = useState<Skill[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isCodePreviewOpen, setIsCodePreviewOpen] = useState(false);
  const [isAgentSkillViewerOpen, setIsAgentSkillViewerOpen] = useState(false);
  const [agentSkillViewerMode, setAgentSkillViewerMode] = useState<'view' | 'edit'>('view');
  const [isTesterModalOpen, setIsTesterModalOpen] = useState(false);
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);
  useEffect(() => {
    loadSkills();
  }, []);

  useEffect(() => {
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      setFilteredSkills(
        skills.filter(
          (skill) =>
            skill.name.toLowerCase().includes(query) ||
            skill.description.toLowerCase().includes(query)
        )
      );
    } else {
      setFilteredSkills(skills);
    }
  }, [searchQuery, skills]);

  const loadSkills = async () => {
    try {
      setIsLoading(true);
      const data = await skillsApi.getAll();
      setSkills(data);
      setFilteredSkills(data);
    } catch (error) {
      console.error('Failed to load skills:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreateSkill = async (data: CreateSkillRequest) => {
    try {
      await skillsApi.create(data);
      await loadSkills();
    } catch (error) {
      console.error('Failed to create skill:', error);
      // Error notification is handled by apiClient interceptor
      throw error;
    }
  };

  const handleEditSkill = (skill: Skill) => {
    setSelectedSkill(skill);
    // Use different editor based on skill type
    if (skill.skill_type === 'agent_skill') {
      setAgentSkillViewerMode('edit');
      setIsAgentSkillViewerOpen(true);
    } else {
      setIsEditModalOpen(true);
    }
  };

  const handleUpdateSkill = async (skillId: string, data: any) => {
    try {
      await skillsApi.update(skillId, data);
      await loadSkills();
    } catch (error) {
      console.error('Failed to update skill:', error);
      throw error;
    }
  };

  const handleViewCode = (skill: Skill) => {
    setSelectedSkill(skill);
    // Use different viewer based on skill type
    if (skill.skill_type === 'agent_skill') {
      setAgentSkillViewerMode('view');
      setIsAgentSkillViewerOpen(true);
    } else {
      setIsCodePreviewOpen(true);
    }
  };

  const handleDeleteSkill = async (skillId: string) => {
    if (!confirm(t('skills.deleteConfirm'))) {
      return;
    }

    try {
      await skillsApi.delete(skillId);
      await loadSkills();
    } catch (error) {
      console.error('Failed to delete skill:', error);
    }
  };

  const handleToggleActive = async (skillId: string, currentlyActive: boolean) => {
    try {
      if (currentlyActive) {
        await skillsApi.deactivateSkill(skillId);
      } else {
        await skillsApi.activateSkill(skillId);
      }
      await loadSkills();
    } catch (error) {
      console.error('Failed to toggle skill status:', error);
    }
  };

  const handleTestSkill = (skill: Skill) => {
    setSelectedSkill(skill);
    setIsTesterModalOpen(true);
  };

  return (
    <div>
      <div className="max-w-7xl mx-auto p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-foreground mb-2 bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">
              {t('skills.title')}
            </h1>
            <p className="text-muted-foreground">
              {t('skills.subtitle')}
            </p>
          </div>
          <button
            onClick={() => setIsAddModalOpen(true)}
            className="flex items-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-primary to-primary/80 hover:from-primary/90 hover:to-primary/70 text-primary-foreground transition-all duration-300 shadow-lg hover:shadow-primary/25 hover:-translate-y-0.5"
          >
            <Plus className="w-5 h-5" />
            {t('skills.addSkill')}
          </button>
        </div>

        {/* Search and Filter Bar */}
        <div className="glass-panel p-6 rounded-2xl shadow-xl">
          <div className="flex items-center gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={t('skills.searchPlaceholder')}
                className="w-full pl-12 pr-4 py-3 rounded-xl bg-muted/30 border border-border/50 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 transition-all"
              />
            </div>
            <button
              onClick={loadSkills}
              disabled={isLoading}
              className="p-3 rounded-xl bg-muted/30 hover:bg-muted/50 text-foreground transition-all duration-300 disabled:opacity-50 hover:shadow-lg"
              title={t('skills.refresh')}
            >
              <RefreshCw className={`w-5 h-5 ${isLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="glass-panel p-6 rounded-2xl shadow-xl hover:shadow-2xl transition-all duration-300 hover:-translate-y-1">
            <div className="flex items-center justify-between mb-2">
              <div className="text-sm font-medium text-muted-foreground">{t('skills.totalSkills')}</div>
              <Package className="w-5 h-5 text-primary/60" />
            </div>
            <div className="text-3xl font-bold bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">
              {skills.length}
            </div>
          </div>
          <div className="glass-panel p-6 rounded-2xl shadow-xl hover:shadow-2xl transition-all duration-300 hover:-translate-y-1">
            <div className="flex items-center justify-between mb-2">
              <div className="text-sm font-medium text-muted-foreground">{t('skills.filteredResults')}</div>
              <Search className="w-5 h-5 text-primary/60" />
            </div>
            <div className="text-3xl font-bold bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">
              {filteredSkills.length}
            </div>
          </div>
          <div className="glass-panel p-6 rounded-2xl shadow-xl hover:shadow-2xl transition-all duration-300 hover:-translate-y-1">
            <div className="flex items-center justify-between mb-2">
              <div className="text-sm font-medium text-muted-foreground">{t('skills.withDependencies')}</div>
              <Layers className="w-5 h-5 text-primary/60" />
            </div>
            <div className="text-3xl font-bold bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">
              {skills.filter((s) => s.dependencies && s.dependencies.length > 0).length}
            </div>
          </div>
        </div>

        {/* Skills Grid */}
        {isLoading ? (
          <div className="flex items-center justify-center py-20">
            <div className="text-center">
              <div className="relative">
                <div className="w-16 h-16 border-4 border-primary/20 border-t-primary rounded-full animate-spin mx-auto mb-4"></div>
                <Package className="w-8 h-8 text-primary absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
              </div>
              <p className="text-muted-foreground font-medium">{t('skills.loading')}</p>
            </div>
          </div>
        ) : filteredSkills.length === 0 ? (
          <div className="glass-panel p-16 rounded-2xl shadow-xl text-center">
            <div className="max-w-md mx-auto">
              <div className="w-20 h-20 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-6">
                <Package className="w-10 h-10 text-primary" />
              </div>
              <h3 className="text-xl font-bold text-foreground mb-3">
                {searchQuery ? t('skills.noSkillsFound') : t('skills.noSkillsYet')}
              </h3>
              <p className="text-muted-foreground mb-6">
                {searchQuery
                  ? t('skills.tryAdjusting')
                  : t('skills.getStarted')}
              </p>
              {!searchQuery && (
                <button
                  onClick={() => setIsAddModalOpen(true)}
                  className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-primary to-primary/80 hover:from-primary/90 hover:to-primary/70 text-primary-foreground transition-all duration-300 shadow-lg hover:shadow-primary/25 hover:-translate-y-0.5"
                >
                  <Plus className="w-5 h-5" />
                  {t('skills.addSkill')}
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredSkills.map((skill) => (
              <SkillCardV2
                key={skill.skill_id}
                skill={skill}
                onEdit={handleEditSkill}
                onDelete={handleDeleteSkill}
                onToggleActive={handleToggleActive}
                onViewCode={handleViewCode}
                onTest={handleTestSkill}
              />
            ))}
          </div>
        )}

        {/* Add Skill Modal */}
        <AddSkillModalV2
          isOpen={isAddModalOpen}
          onClose={() => setIsAddModalOpen(false)}
          onSubmit={handleCreateSkill}
        />

        {/* Edit Skill Modal */}
        {selectedSkill && (
          <EditSkillModal
            isOpen={isEditModalOpen}
            onClose={() => {
              setIsEditModalOpen(false);
              setSelectedSkill(null);
            }}
            onSubmit={handleUpdateSkill}
            skill={selectedSkill}
          />
        )}

        {/* Code Preview Modal */}
        {selectedSkill && (
          <CodePreviewModal
            isOpen={isCodePreviewOpen}
            onClose={() => {
              setIsCodePreviewOpen(false);
              setSelectedSkill(null);
            }}
            skill={selectedSkill}
          />
        )}

        {/* Agent Skill Viewer */}
        {selectedSkill && (
          <AgentSkillViewer
            isOpen={isAgentSkillViewerOpen}
            onClose={() => {
              setIsAgentSkillViewerOpen(false);
              setSelectedSkill(null);
              setAgentSkillViewerMode('view');
            }}
            skillId={selectedSkill.skill_id}
            skillName={selectedSkill.name}
            mode={agentSkillViewerMode}
            onUpdate={loadSkills}
          />
        )}

        {/* Skill Tester Modal */}
        {selectedSkill && (
          <SkillTesterModal
            isOpen={isTesterModalOpen}
            onClose={() => {
              setIsTesterModalOpen(false);
              setSelectedSkill(null);
            }}
            skillId={selectedSkill.skill_id}
            skillName={selectedSkill.name}
            skillType={selectedSkill.skill_type}
            interfaceDefinition={selectedSkill.interface_definition}
          />
        )}
      </div>
    </div>
  );
}
