
import React, { useState } from 'react';
import { Agent, AgentStatus } from '../types';
import { AGENT_TEMPLATES } from '../constants';
import { Plus, Search, Filter, MoreVertical, Shield, Zap, X } from 'lucide-react';
import { TranslationType } from '../translations';

interface Props {
  agents: Agent[];
  setAgents: React.Dispatch<React.SetStateAction<Agent[]>>;
  t: TranslationType['workforce'];
}

const Workforce: React.FC<Props> = ({ agents, setAgents, t }) => {
  const [showAddModal, setShowAddModal] = useState(false);
  const [search, setSearch] = useState('');

  const createFromTemplate = (template: typeof AGENT_TEMPLATES[0]) => {
    const newAgent: Agent = {
      id: Math.random().toString(36).substr(2, 9),
      name: `${template.type.split(' ')[0]}-${Math.floor(Math.random() * 1000)}`,
      type: template.type,
      description: template.description,
      skills: template.skills,
      status: AgentStatus.IDLE,
      avatar: template.avatar
    };
    setAgents(prev => [...prev, newAgent]);
    setShowAddModal(false);
  };

  const filteredAgents = agents.filter(a => 
    a.name.toLowerCase().includes(search.toLowerCase()) || 
    a.type.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-10 animate-in fade-in slide-in-from-bottom-6 duration-700">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6">
        <div>
          <h1 className="text-4xl font-bold tracking-tight mb-2">{t.title}</h1>
          <p className="text-zinc-500 dark:text-zinc-400 font-medium">{t.subtitle}</p>
        </div>
        <button 
          onClick={() => setShowAddModal(true)}
          className="bg-emerald-500 hover:bg-emerald-600 text-white dark:text-black px-8 py-3 rounded-full font-bold transition-all flex items-center gap-2 shadow-lg shadow-emerald-500/10 active:scale-95"
        >
          <Plus className="w-5 h-5" /> {t.deploy}
        </button>
      </div>

      <div className="flex gap-4 items-center bg-zinc-500/5 p-2 rounded-2xl border border-zinc-500/10">
        <div className="relative flex-1">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400" />
          <input 
            type="text" 
            placeholder={t.searchPlaceholder}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-transparent border-none py-3 pl-12 pr-4 focus:ring-0 text-sm placeholder:text-zinc-400"
          />
        </div>
        <button className="flex items-center gap-2 px-5 py-2.5 hover:bg-white/10 rounded-xl transition-all text-sm font-semibold text-zinc-500">
          <Filter className="w-4 h-4" /> {t.filter}
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
        {filteredAgents.map(agent => (
          <div key={agent.id} className="glass-panel group relative rounded-[32px] overflow-hidden p-8 hover:translate-y-[-4px]">
            <div className="flex justify-between items-start mb-8">
              <div className="relative">
                <div className="w-20 h-20 rounded-[24px] overflow-hidden border-2 border-white dark:border-zinc-800 shadow-2xl">
                  <img src={agent.avatar} alt={agent.name} className="w-full h-full object-cover" />
                </div>
                <div className={`absolute -bottom-1 -right-1 w-6 h-6 rounded-full border-4 border-white dark:border-black shadow-lg flex items-center justify-center ${
                  agent.status === AgentStatus.WORKING ? 'bg-emerald-500' : 
                  agent.status === AgentStatus.IDLE ? 'bg-zinc-400' : 'bg-red-500'
                }`}>
                  {agent.status === AgentStatus.WORKING && <Zap className="w-3.5 h-3.5 text-white" />}
                </div>
              </div>
              <button className="p-2.5 hover:bg-zinc-500/5 rounded-full text-zinc-400 transition-colors">
                <MoreVertical className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <h3 className="text-2xl font-bold tracking-tight mb-1">{agent.name}</h3>
                <div className="flex items-center gap-2">
                  <Shield className="w-3.5 h-3.5 text-emerald-600" />
                  <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-600">{agent.type}</span>
                </div>
              </div>
              
              <p className="text-zinc-500 dark:text-zinc-400 text-sm leading-relaxed line-clamp-2">{agent.description}</p>
              
              <div className="flex flex-wrap gap-2 pt-2">
                {agent.skills.map(skill => (
                  <span key={skill} className="px-3 py-1.5 bg-zinc-500/5 rounded-lg text-[10px] font-bold text-zinc-600 dark:text-zinc-300 uppercase tracking-tight border border-zinc-500/5">
                    {skill}
                  </span>
                ))}
              </div>
            </div>

            <div className="mt-8 pt-6 border-t border-zinc-500/5 flex justify-between items-center">
              <span className="text-[10px] text-zinc-400 font-bold uppercase tracking-widest">{t.memoryUsage}: 1.2GB</span>
              <button className="text-xs font-bold text-emerald-600 hover:text-emerald-500 transition-colors uppercase tracking-widest">{t.viewLogs}</button>
            </div>
          </div>
        ))}
      </div>

      {showAddModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-black/10 dark:bg-black/60 backdrop-blur-xl animate-in fade-in duration-500">
          <div className="glass-panel w-full max-w-2xl rounded-[40px] overflow-hidden">
            <div className="p-10 flex justify-between items-center border-b border-zinc-500/5">
              <h2 className="text-3xl font-bold tracking-tight">{t.modalTitle}</h2>
              <button onClick={() => setShowAddModal(false)} className="p-3 hover:bg-zinc-500/5 rounded-full transition-colors">
                <X className="w-6 h-6 text-zinc-400" />
              </button>
            </div>
            <div className="p-10 grid grid-cols-1 md:grid-cols-2 gap-8 overflow-y-auto max-h-[65vh] custom-scrollbar">
              {AGENT_TEMPLATES.map((tmpl, idx) => (
                <div 
                  key={idx} 
                  onClick={() => createFromTemplate(tmpl)}
                  className="p-8 rounded-[32px] border border-zinc-500/5 hover:border-emerald-500/20 hover:bg-emerald-500/5 transition-all cursor-pointer group"
                >
                  <div className="w-14 h-14 rounded-2xl overflow-hidden mb-6 shadow-xl grayscale group-hover:grayscale-0 transition-all duration-500">
                    <img src={tmpl.avatar} alt="" className="w-full h-full object-cover" />
                  </div>
                  <h3 className="text-xl font-bold mb-3 group-hover:text-emerald-600 transition-colors">{tmpl.type}</h3>
                  <p className="text-zinc-500 text-sm mb-6 leading-relaxed line-clamp-2">{tmpl.description}</p>
                  <div className="flex flex-wrap gap-2">
                    {tmpl.skills.slice(0, 3).map(s => (
                      <span key={s} className="text-[10px] bg-white/50 dark:bg-zinc-900 px-2.5 py-1 rounded-lg text-zinc-400 font-bold border border-zinc-500/5 uppercase tracking-tight">{s}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Workforce;
