import React, { useState } from 'react';
import { X, Send, HelpCircle } from 'lucide-react';
import { LayoutModal } from '@/components/LayoutModal';
import { ModalPanel } from '@/components/ModalPanel';

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

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
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
      closeOnBackdropClick={false}
      closeOnEscape={true}
    >
      <ModalPanel className="w-full max-w-2xl max-h-[calc(100vh-var(--app-header-height,4rem)-3rem)] overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <HelpCircle className="w-6 h-6 text-yellow-500" />
            <h2 className="text-2xl font-bold text-gray-800 dark:text-white">
              Clarification Needed
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/20 rounded-lg transition-colors"
          >
            <X className="w-6 h-6 text-gray-700 dark:text-gray-300" />
          </button>
        </div>

        <p className="text-gray-600 dark:text-gray-400 mb-6">
          Please provide additional information to help us better understand your goal:
        </p>

        <form onSubmit={handleSubmit}>
          <div className="space-y-4 mb-6">
            {questions.map((question, index) => (
              <div key={index}>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  {index + 1}. {question}
                </label>
                <textarea
                  value={answers[index]}
                  onChange={(e) => handleAnswerChange(index, e.target.value)}
                  placeholder="Your answer..."
                  rows={3}
                  className="w-full px-4 py-2 bg-white/50 dark:bg-black/20 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-gray-800 dark:text-white resize-none"
                  required
                />
              </div>
            ))}
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-3 bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-white rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors font-medium"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!answers.every((a) => a.trim())}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Send className="w-5 h-5" />
              Submit Answers
            </button>
          </div>
        </form>
      </ModalPanel>
    </LayoutModal>
  );
};
