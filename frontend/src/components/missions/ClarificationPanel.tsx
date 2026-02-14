import React, { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Send, MessageSquare } from 'lucide-react';
import { useMissionStore } from '@/stores/missionStore';

interface ClarificationPanelProps {
  missionId: string;
  isOpen: boolean;
  onClose: () => void;
}

export const ClarificationPanel: React.FC<ClarificationPanelProps> = ({
  missionId,
  isOpen,
  onClose,
}) => {
  const { t } = useTranslation();
  const { missionEvents, clarify } = useMissionStore();
  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const clarificationEvents = missionEvents.filter(
    (e) =>
      e.event_type === 'clarification_request' || e.event_type === 'clarification_response'
  );

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [clarificationEvents.length]);

  const handleSend = async () => {
    if (!input.trim() || isSending) return;
    setIsSending(true);
    try {
      await clarify(missionId, input.trim());
      setInput('');
    } finally {
      setIsSending(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed right-0 top-0 h-full w-96 glass-panel border-l border-zinc-200 dark:border-zinc-700 z-40 flex flex-col animate-in slide-in-from-right duration-300" style={{ marginLeft: 'var(--sidebar-width, 0px)' }}>
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-zinc-200 dark:border-zinc-700">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-4 h-4 text-emerald-500" />
          <h3 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
            {t('missions.clarification')}
          </h3>
        </div>
        <button
          onClick={onClose}
          className="p-1 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors"
        >
          <X className="w-4 h-4 text-zinc-500" />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {clarificationEvents.length === 0 && (
          <div className="text-center text-zinc-400 text-sm py-8">
            No messages yet
          </div>
        )}
        {clarificationEvents.map((event) => {
          const isLeader = event.event_type === 'clarification_request';
          return (
            <div
              key={event.event_id}
              className={`flex ${isLeader ? 'justify-start' : 'justify-end'}`}
            >
              <div
                className={`max-w-[80%] px-3 py-2 rounded-xl text-sm ${
                  isLeader
                    ? 'bg-zinc-100 dark:bg-zinc-800 text-zinc-800 dark:text-zinc-200'
                    : 'bg-emerald-500 text-white'
                }`}
              >
                <p className="whitespace-pre-wrap">{event.message}</p>
                <span className="block text-[10px] mt-1 opacity-60">
                  {new Date(event.created_at).toLocaleTimeString()}
                </span>
              </div>
            </div>
          );
        })}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-zinc-200 dark:border-zinc-700">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type your response..."
            rows={2}
            className="flex-1 resize-none rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 px-3 py-2 text-sm text-zinc-800 dark:text-zinc-200 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isSending}
            className="p-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
};
