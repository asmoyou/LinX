import { useState, useEffect } from 'react';
import { Plus, Search, RefreshCw, Package } from 'lucide-react';
import SkillCardV2 from '@/components/skills/SkillCardV2';
import AddSkillModalV2 from '@/components/skills/AddSkillModalV2';
import EditSkillModal from '@/components/skills/EditSkillModal';
import CodePreviewModal from '@/components/skills/CodePreviewModal';
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
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);
  const [isRegisteringDefaults, setIsRegisteringDefaults] = useState(false);

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
      throw error;
    }
  };

  const handleEditSkill = (skill: Skill) => {
    setSelectedSkill(skill);
    setIsEditModalOpen(true);
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
    setIsCodePreviewOpen(true);
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

  const handleRegisterDefaults = async () => {
    try {
      setIsRegisteringDefaults(true);
      const result = await skillsApi.registerDefaults();
      alert(`Successfully registered ${result.registered_count} default skills`);
      await loadSkills();
    } catch (error) {
      console.error('Failed to register default skills:', error);
      alert('Failed to register default skills');
    } finally {
      setIsRegisteringDefaults(false);
    }
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-foreground mb-2">{t('skills.title')}</h1>
          <p className="text-muted-foreground">
            {t('skills.subtitle')}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleRegisterDefaults}
            disabled={isRegisteringDefaults}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-muted/50 hover:bg-muted text-foreground transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Package className="w-4 h-4" />
            {isRegisteringDefaults ? t('skills.registering') : t('skills.registerDefaults')}
          </button>
          <button
            onClick={() => setIsAddModalOpen(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground transition-colors"
          >
            <Plus className="w-4 h-4" />
            {t('skills.addSkill')}
          </button>
        </div>
      </div>

      {/* Search and Filter Bar */}
      <div className="glass-panel p-4">
        <div className="flex items-center gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('skills.searchPlaceholder')}
              className="w-full pl-10 pr-4 py-2 rounded-lg bg-muted/50 border border-border/50 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
            />
          </div>
          <button
            onClick={loadSkills}
            disabled={isLoading}
            className="p-2 rounded-lg bg-muted/50 hover:bg-muted text-foreground transition-colors disabled:opacity-50"
            title={t('skills.refresh')}
          >
            <RefreshCw className={`w-5 h-5 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="glass-panel p-4">
          <div className="text-sm text-muted-foreground mb-1">{t('skills.totalSkills')}</div>
          <div className="text-2xl font-bold text-foreground">{skills.length}</div>
        </div>
        <div className="glass-panel p-4">
          <div className="text-sm text-muted-foreground mb-1">{t('skills.filteredResults')}</div>
          <div className="text-2xl font-bold text-foreground">{filteredSkills.length}</div>
        </div>
        <div className="glass-panel p-4">
          <div className="text-sm text-muted-foreground mb-1">{t('skills.withDependencies')}</div>
          <div className="text-2xl font-bold text-foreground">
            {skills.filter((s) => s.dependencies && s.dependencies.length > 0).length}
          </div>
        </div>
      </div>

      {/* Skills Grid */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="text-center">
            <RefreshCw className="w-8 h-8 text-primary animate-spin mx-auto mb-2" />
            <p className="text-muted-foreground">{t('skills.loading')}</p>
          </div>
        </div>
      ) : filteredSkills.length === 0 ? (
        <div className="glass-panel p-12 text-center">
          <Package className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-foreground mb-2">
            {searchQuery ? t('skills.noSkillsFound') : t('skills.noSkillsYet')}
          </h3>
          <p className="text-muted-foreground mb-4">
            {searchQuery
              ? t('skills.tryAdjusting')
              : t('skills.getStarted')}
          </p>
          {!searchQuery && (
            <div className="flex items-center justify-center gap-3">
              <button
                onClick={handleRegisterDefaults}
                disabled={isRegisteringDefaults}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-muted/50 hover:bg-muted text-foreground transition-colors"
              >
                <Package className="w-4 h-4" />
                {t('skills.registerDefaults')}
              </button>
              <button
                onClick={() => setIsAddModalOpen(true)}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground transition-colors"
              >
                <Plus className="w-4 h-4" />
                {t('skills.addSkill')}
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredSkills.map((skill) => (
            <SkillCardV2
              key={skill.skill_id}
              skill={skill}
              onEdit={handleEditSkill}
              onDelete={handleDeleteSkill}
              onViewCode={handleViewCode}
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
    </div>
  );
}
