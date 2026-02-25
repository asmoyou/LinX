import React, { useState } from 'react';
import { Send, HelpCircle } from 'lucide-react';
import { LayoutModal } from '@/components/LayoutModal';

interface ClarificationModalProps {
  isOpen: boolean;
  questions: string[];
  onClose: () => void;
  onSubmit: (answers: string[]) => void;
}

export const ClarificationModal: React.FC<ClarificationModalProps> = ({
  isOpen,
  questions,
  onClose,
  onSubmit,
}) => {
  const [answers, setAnswers] = useState<string[]>(new Array(questions.length).fill(''));

  if (!isOpen) return null;

  const handleSubmit = () => {
    if (answers.every((a) => a.trim())) {
      onSubmit(answers);
      setAnswers(new Array(questions.length).fill(''));
      onClose();
    }
  };

  const handleAnswerChange = (index: number, value: string) => {
    const newAnswers = [...answers];
    newAnswers[index] = value;
    setAnswers(newAnswers);
  };

  return (
    <LayoutModal
      isOpen={isOpen}
      onClose={onClose}
      size="2xl"
      title={
        <div className="flex items-center gap-2 text-zinc-900 dark:text-zinc-100">
          <HelpCircle className="w-5 h-5 text-amber-500" />
          <span>Clarification Needed</span>
        </div>
      }
      description="Please provide additional information to help us better understand your goal:"
      closeOnBackdropClick={false}
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 rounded-lg hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-colors font-medium border border-transparent dark:border-zinc-700"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!answers.every((a) => a.trim())}
            className="flex items-center justify-center gap-2 px-4 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
          >
            <Send className="w-4 h-4" />
            Submit Answers
          </button>
        </>
      }
    >
      <div className="space-y-6">
        {questions.map((question, index) => (
          <div key={index} className="space-y-2">
            <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300">
              <span className="text-emerald-500 mr-1">{index + 1}.</span> {question}
            </label>
            <textarea
              value={answers[index]}
              onChange={(e) => handleAnswerChange(index, e.target.value)}
              placeholder="Your answer..."
              rows={3}
              className="w-full px-4 py-3 bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500/50 text-zinc-800 dark:text-zinc-200 resize-none transition-shadow"
              required
            />
          </div>
        ))}
      </div>
    </LayoutModal>
  );
};
