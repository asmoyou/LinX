import { useState, useEffect } from 'react';
import { Plus, Search, RefreshCw, Package } from 'lucide-react';
import SkillCard from '@/components/skills/SkillCard';
import AddSkillModal from '@/components/skills/AddSkillModal';
import { skillsApi, type Skill, type CreateSkillRequest } from '@/api/skills';

export default function Skills() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [filteredSkills, setFilteredSkills] = useState<Skill[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
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
    // TODO: Implement edit modal
    console.log('Edit skill:', skill);
  };

  const handleDeleteSkill = async (skillId: string) => {
    if (!confirm('Are you sure you want to delete this skill?')) {
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
          <h1 className="text-3xl font-bold text-foreground mb-2">Skills Library</h1>
          <p className="text-muted-foreground">
            Manage reusable capabilities that can be assigned to agents
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleRegisterDefaults}
            disabled={isRegisteringDefaults}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-muted/50 hover:bg-muted text-foreground transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Package className="w-4 h-4" />
            {isRegisteringDefaults ? 'Registering...' : 'Register Defaults'}
          </button>
          <button
            onClick={() => setIsAddModalOpen(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground transition-colors"
          >
            <Plus className="w-4 h-4" />
            Add Skill
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
              placeholder="Search skills by name or description..."
              className="w-full pl-10 pr-4 py-2 rounded-lg bg-muted/50 border border-border/50 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
            />
          </div>
          <button
            onClick={loadSkills}
            disabled={isLoading}
            className="p-2 rounded-lg bg-muted/50 hover:bg-muted text-foreground transition-colors disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw className={`w-5 h-5 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="glass-panel p-4">
          <div className="text-sm text-muted-foreground mb-1">Total Skills</div>
          <div className="text-2xl font-bold text-foreground">{skills.length}</div>
        </div>
        <div className="glass-panel p-4">
          <div className="text-sm text-muted-foreground mb-1">Filtered Results</div>
          <div className="text-2xl font-bold text-foreground">{filteredSkills.length}</div>
        </div>
        <div className="glass-panel p-4">
          <div className="text-sm text-muted-foreground mb-1">With Dependencies</div>
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
            <p className="text-muted-foreground">Loading skills...</p>
          </div>
        </div>
      ) : filteredSkills.length === 0 ? (
        <div className="glass-panel p-12 text-center">
          <Package className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-foreground mb-2">
            {searchQuery ? 'No skills found' : 'No skills yet'}
          </h3>
          <p className="text-muted-foreground mb-4">
            {searchQuery
              ? 'Try adjusting your search query'
              : 'Get started by adding your first skill or registering default skills'}
          </p>
          {!searchQuery && (
            <div className="flex items-center justify-center gap-3">
              <button
                onClick={handleRegisterDefaults}
                disabled={isRegisteringDefaults}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-muted/50 hover:bg-muted text-foreground transition-colors"
              >
                <Package className="w-4 h-4" />
                Register Defaults
              </button>
              <button
                onClick={() => setIsAddModalOpen(true)}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground transition-colors"
              >
                <Plus className="w-4 h-4" />
                Add Skill
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredSkills.map((skill) => (
            <SkillCard
              key={skill.skill_id}
              skill={skill}
              onEdit={handleEditSkill}
              onDelete={handleDeleteSkill}
            />
          ))}
        </div>
      )}

      {/* Add Skill Modal */}
      <AddSkillModal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        onSubmit={handleCreateSkill}
      />
    </div>
  );
}
