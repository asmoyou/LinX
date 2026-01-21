import React, { useState } from 'react';
import { Send, Loader2, Sparkles } from 'lucide-react';

interface GoalInputProps {
  onSubmit: (title: string, description: string) => void;
  isLoading: boolean;
}

export const GoalInput: React.FC<GoalInputProps> = ({ onSubmit, isLoading }) => {
  const [input, setInput] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim()) {
      // Use the input as both title and description for simplicity
      onSubmit(input, input);
      setInput('');
    }
  };

  return (
    <form onSubmit={handleSubmit} className="relative group">
      <div className="glass-panel p-3 rounded-[32px] flex items-center transition-all duration-500 focus-within:ring-4 focus-within:ring-emerald-500/10">
        <div className="p-4">
          <Sparkles className="w-7 h-7 text-emerald-500" />
        </div>
        <input 
          type="text" 
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={isLoading}
          placeholder="Describe your goal in natural language..." 
          className="flex-1 bg-transparent border-none py-6 text-xl focus:ring-0 placeholder:text-zinc-400 font-medium text-zinc-800 dark:text-zinc-200"
        />
        <button 
          type="submit"
          disabled={!input.trim() || isLoading}
          className="bg-emerald-500 hover:bg-emerald-600 disabled:bg-zinc-200 dark:disabled:bg-zinc-800 disabled:text-zinc-400 text-white dark:text-black px-10 py-5 rounded-[24px] font-bold flex items-center gap-3 transition-all active:scale-95 shadow-xl shadow-emerald-500/10"
        >
          {isLoading ? (
            <Loader2 className="w-6 h-6 animate-spin" />
          ) : (
            <Send className="w-6 h-6" />
          )}
          Execute
        </button>
      </div>
    </form>
  );
};
