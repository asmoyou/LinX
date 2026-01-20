
import React, { useState } from 'react';
import { 
  FileText, 
  Search, 
  Upload, 
  HardDrive, 
  Lock, 
  Eye, 
  Download, 
  Trash2,
  Image as ImageIcon,
  Mic,
  Video,
  ChevronRight
} from 'lucide-react';
import { TranslationType } from '../translations';

interface Props {
  t: TranslationType['knowledge'];
}

const KnowledgeBase: React.FC<Props> = ({ t }) => {
  const [files] = useState([
    { id: '1', title: 'Corporate_Security_Policy.pdf', size: '2.4 MB', type: 'PDF', date: '2023-12-01' },
    { id: '2', title: 'Q3_Financial_Analysis.docx', size: '1.1 MB', type: 'DOCX', date: '2023-11-28' },
    { id: '3', title: 'Marketing_Voice_Over.wav', size: '14.5 MB', type: 'AUDIO', date: '2023-11-15' },
    { id: '4', title: 'Brand_Identity_v2.png', size: '4.2 MB', type: 'IMAGE', date: '2023-11-10' },
  ]);

  const getIcon = (type: string) => {
    switch(type) {
      case 'PDF': return <FileText className="text-red-500" />;
      case 'AUDIO': return <Mic className="text-blue-500" />;
      case 'IMAGE': return <ImageIcon className="text-emerald-500" />;
      case 'VIDEO': return <Video className="text-purple-500" />;
      default: return <FileText className="text-zinc-500" />;
    }
  };

  return (
    <div className="space-y-10 animate-in fade-in slide-in-from-bottom-6 duration-700">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6">
        <div>
          <h1 className="text-4xl font-bold tracking-tight mb-2">{t.title}</h1>
          <p className="text-zinc-500 dark:text-zinc-400 font-medium">{t.subtitle}</p>
        </div>
        <div className="flex gap-3 w-full sm:w-auto">
          <button className="flex-1 sm:flex-none flex items-center justify-center gap-2 px-6 py-3 rounded-full border border-zinc-500/10 hover:bg-zinc-500/5 transition-all font-bold text-sm">
            <Lock className="w-4 h-4" /> {t.permissions}
          </button>
          <button className="flex-1 sm:flex-none bg-emerald-500 text-white dark:text-black px-8 py-3 rounded-full font-bold transition-all flex items-center justify-center gap-2 shadow-lg shadow-emerald-500/10 hover:bg-emerald-600 active:scale-95">
            <Upload className="w-4 h-4" /> {t.upload}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
        <div className="lg:col-span-1 space-y-6">
          <div className="glass-panel p-8 rounded-[32px]">
            <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-400 mb-8">{t.nodes}</h3>
            <div className="space-y-6">
              <div className="flex items-center gap-4">
                <div className="p-2.5 rounded-xl bg-emerald-500/10 text-emerald-600">
                  <HardDrive className="w-5 h-5" />
                </div>
                <div className="flex-1">
                  <div className="flex justify-between items-end mb-1.5">
                    <p className="text-xs font-bold">MinIO Storage</p>
                    <span className="text-[10px] font-mono text-zinc-500">65%</span>
                  </div>
                  <div className="w-full bg-zinc-500/10 h-1.5 rounded-full overflow-hidden">
                    <div className="bg-emerald-500 h-full w-[65%]"></div>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <div className="p-2.5 rounded-xl bg-blue-500/10 text-blue-600">
                  <HardDrive className="w-5 h-5" />
                </div>
                <div className="flex-1">
                  <div className="flex justify-between items-end mb-1.5">
                    <p className="text-xs font-bold">Milvus Index</p>
                    <span className="text-[10px] font-mono text-zinc-500">22%</span>
                  </div>
                  <div className="w-full bg-zinc-500/10 h-1.5 rounded-full overflow-hidden">
                    <div className="bg-blue-500 h-full w-[22%]"></div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="glass-panel p-8 rounded-[32px]">
            <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-400 mb-6">{t.contentTypes}</h3>
            <div className="space-y-1">
              {['Documents', 'Images', 'Multimedia', 'Policies', 'Research'].map(type => (
                <button key={type} className="w-full flex justify-between items-center py-2.5 px-4 rounded-xl hover:bg-zinc-500/5 text-sm font-medium transition-colors text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-white group">
                  <span>{type}</span>
                  <ChevronRight className="w-4 h-4 text-zinc-300 group-hover:translate-x-1 transition-transform" />
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="lg:col-span-3 space-y-8">
          <div className="relative group">
            <Search className="absolute left-5 top-1/2 -translate-y-1/2 w-5 h-5 text-zinc-400" />
            <input 
              type="text" 
              placeholder={t.searchPlaceholder}
              className="w-full bg-zinc-500/5 border border-zinc-500/10 rounded-[24px] py-5 pl-14 pr-6 focus:ring-4 focus:ring-emerald-500/5 outline-none text-lg transition-all"
            />
          </div>

          <div className="glass-panel rounded-[32px] overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="bg-zinc-500/5 text-zinc-400 text-[10px] font-bold uppercase tracking-[0.2em]">
                    <th className="px-8 py-5">{t.table.name}</th>
                    <th className="px-8 py-5">{t.table.type}</th>
                    <th className="px-8 py-5">{t.table.size}</th>
                    <th className="px-8 py-5">{t.table.modified}</th>
                    <th className="px-8 py-5 text-right">{t.table.actions}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-500/5">
                  {files.map(file => (
                    <tr key={file.id} className="hover:bg-zinc-500/5 transition-colors group">
                      <td className="px-8 py-6">
                        <div className="flex items-center gap-4">
                          <div className="w-10 h-10 rounded-xl bg-white dark:bg-zinc-800 shadow-sm flex items-center justify-center border border-zinc-500/5">
                            {getIcon(file.type)}
                          </div>
                          <span className="font-bold text-sm tracking-tight">{file.title}</span>
                        </div>
                      </td>
                      <td className="px-8 py-6">
                        <span className="text-[10px] font-bold px-2.5 py-1 bg-zinc-500/10 rounded-lg text-zinc-500 uppercase tracking-tighter">{file.type}</span>
                      </td>
                      <td className="px-8 py-6 text-xs font-medium text-zinc-500">{file.size}</td>
                      <td className="px-8 py-6 text-xs font-medium text-zinc-500">{file.date}</td>
                      <td className="px-8 py-6 text-right">
                        <div className="flex justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity translate-x-2 group-hover:translate-x-0 transition-all duration-300">
                          <button className="p-2.5 hover:bg-zinc-200 dark:hover:bg-zinc-700 rounded-xl transition-colors text-zinc-400 hover:text-zinc-900 dark:hover:text-white"><Eye className="w-4 h-4" /></button>
                          <button className="p-2.5 hover:bg-zinc-200 dark:hover:bg-zinc-700 rounded-xl transition-colors text-zinc-400 hover:text-zinc-900 dark:hover:text-white"><Download className="w-4 h-4" /></button>
                          <button className="p-2.5 hover:bg-red-500/10 text-red-500 rounded-xl transition-colors"><Trash2 className="w-4 h-4" /></button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default KnowledgeBase;
