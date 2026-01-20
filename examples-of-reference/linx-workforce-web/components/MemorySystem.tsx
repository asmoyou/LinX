
import React, { useState } from 'react';
import { 
  Zap, 
  User, 
  Building2, 
  Search, 
  Tag, 
  ShieldAlert,
  Terminal,
  Share2
} from 'lucide-react';
import { TranslationType } from '../translations';

interface Props {
  t: TranslationType['memory'];
}

const MemorySystem: React.FC<Props> = ({ t }) => {
  const [activeLayer, setActiveLayer] = useState<'USER' | 'COMPANY' | 'AGENT'>('COMPANY');

  const memories = [
    { id: 'm1', content: "User preferred 100-word summaries for all technical reports.", type: 'USER', date: '2h ago', tags: ['Preference', 'Reporting'] },
    { id: 'm2', content: "Completed analysis of Project Hydra reveals 12% bottleneck in frontend pipeline.", type: 'COMPANY', date: '5h ago', tags: ['Project Hydra', 'Bottleneck'] },
    { id: 'm3', content: "Agent Scribe-7 successfully learned the new GraphQL schema format.", type: 'AGENT', date: '1d ago', tags: ['Learning', 'GraphQL'] },
    { id: 'm4', content: "Company-wide Q4 goals: 20% growth in SaaS revenue.", type: 'COMPANY', date: '2d ago', tags: ['Strategy', 'Finance'] },
  ];

  const filtered = memories.filter(m => m.type === activeLayer);

  return (
    <div className="space-y-10 animate-in fade-in slide-in-from-bottom-6 duration-700">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-end gap-6">
        <div>
          <h1 className="text-4xl font-bold tracking-tight mb-2">{t.title}</h1>
          <p className="text-zinc-500 dark:text-zinc-400 font-medium">{t.subtitle}</p>
        </div>
        <div className="flex p-1 bg-zinc-500/5 rounded-2xl border border-zinc-500/10 backdrop-blur-md">
          {(['COMPANY', 'USER', 'AGENT'] as const).map(layer => (
            <button
              key={layer}
              onClick={() => setActiveLayer(layer)}
              className={`px-6 py-2.5 rounded-xl text-xs font-bold uppercase tracking-widest transition-all duration-300 ${
                activeLayer === layer ? 'bg-white dark:bg-zinc-700 shadow-sm text-emerald-600 dark:text-emerald-400' : 'text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200'
              }`}
            >
              {t.layers[layer.toLowerCase() as keyof typeof t.layers]}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-8">
          <div className="relative group">
            <Search className="absolute left-5 top-1/2 -translate-y-1/2 w-5 h-5 text-zinc-400" />
            <input 
              type="text" 
              placeholder={t.searchPlaceholder}
              className="w-full bg-zinc-500/5 border border-zinc-500/10 rounded-[24px] py-5 pl-14 pr-6 focus:ring-4 focus:ring-emerald-500/5 outline-none transition-all"
            />
          </div>

          <div className="space-y-6">
            {filtered.map(memory => (
              <div key={memory.id} className="glass-panel p-8 rounded-[32px] group hover:translate-y-[-2px]">
                <div className="flex justify-between items-start mb-6">
                  <div className="flex items-center gap-5">
                    <div className={`p-3 rounded-2xl ${
                      memory.type === 'USER' ? 'bg-blue-500/10 text-blue-600' : 
                      memory.type === 'COMPANY' ? 'bg-emerald-500/10 text-emerald-600' : 'bg-purple-500/10 text-purple-600'
                    }`}>
                      {memory.type === 'USER' ? <User className="w-5 h-5" /> : memory.type === 'COMPANY' ? <Building2 className="w-5 h-5" /> : <Zap className="w-5 h-5" />}
                    </div>
                    <div>
                      <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-[0.2em]">{memory.type} MEMORY</span>
                      <h4 className="text-xl font-bold tracking-tight text-zinc-800 dark:text-zinc-100 mt-1">{memory.content}</h4>
                    </div>
                  </div>
                  <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">{memory.date}</span>
                </div>
                <div className="flex justify-between items-center pt-2">
                  <div className="flex gap-2">
                    {memory.tags.map(tag => (
                      <span key={tag} className="flex items-center gap-1.5 text-[10px] font-bold text-zinc-500 bg-zinc-500/5 px-3 py-1.5 rounded-lg border border-zinc-500/5 uppercase tracking-tight">
                        <Tag className="w-3 h-3" /> {tag}
                      </span>
                    ))}
                  </div>
                  <button className="opacity-0 group-hover:opacity-100 transition-all flex items-center gap-2 text-[10px] font-bold text-emerald-600 uppercase tracking-widest hover:underline decoration-2 underline-offset-4">
                    <Share2 className="w-3.5 h-3.5" /> {t.share}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-8">
          <div className="glass-panel p-8 rounded-[32px]">
            <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-400 mb-8 flex items-center gap-3">
              <Terminal className="w-4 h-4 text-emerald-500" /> {t.activity}
            </h3>
            <div className="space-y-8">
              {[
                { label: 'Semantic Queries', val: '4,201/min', color: 'text-emerald-600 dark:text-emerald-400' },
                { label: 'Embedding Latency', val: '42ms', color: 'text-blue-600 dark:text-blue-400' },
                { label: 'Conflict Resolutions', val: '12 today', color: 'text-orange-600 dark:text-orange-400' },
              ].map((stat, i) => (
                <div key={i} className="group">
                  <p className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest mb-2">{stat.label}</p>
                  <p className={`text-3xl font-bold tracking-tight ${stat.color}`}>{stat.val}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="glass-panel p-8 rounded-[32px] bg-red-500/5 border-red-500/10">
            <h3 className="text-[10px] font-bold text-red-600 uppercase tracking-widest mb-3 flex items-center gap-2">
              <ShieldAlert className="w-4 h-4" /> {t.isolation}
            </h3>
            <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400 leading-relaxed">{t.isolationDesc}</p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MemorySystem;
