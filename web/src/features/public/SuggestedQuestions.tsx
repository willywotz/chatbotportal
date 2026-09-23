import { ArrowUpRight, HelpCircle } from 'lucide-react';
import type { PopularQuestion } from '@/features/popular-questions/popularQuestionsApi';
import { AgencyLogo } from '@/shared/components/AgencyLogo';

interface SuggestedQuestionsProps {
  questions: PopularQuestion[];
  onSelect: (question: string) => void;
}

export function SuggestedQuestions({ questions, onSelect }: SuggestedQuestionsProps) {
  return (
    <div className="w-full max-w-xl">
      <p className="text-xs text-muted-foreground mb-3 text-center font-medium">คำถามยอดนิยม</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {questions.map((q) => (
          <button
            key={q.id}
            onClick={() => onSelect(q.text)}
            className="group text-left text-sm bg-card border border-border rounded-2xl p-4 hover:bg-accent hover:border-primary/30 transition-all duration-200 hover:shadow-md flex items-start gap-3"
          >
            {q.agency?.logo ? (
              <span className="text-lg shrink-0 mt-0.5 w-8 h-8 rounded-lg flex items-center justify-center">
                <AgencyLogo logo={q.agency.logo} alt={q.agency.name} className="w-full h-full rounded-lg" />
              </span>
            ) : (
              <span
                aria-label={q.agency ? q.agency.name : 'ไม่ระบุหน่วยงาน'}
                className="shrink-0 mt-0.5 w-8 h-8 rounded-lg flex items-center justify-center bg-muted"
              >
                <HelpCircle className="w-4 h-4 text-muted-foreground" />
              </span>
            )}
            <span className="flex-1">{q.text}</span>
            <ArrowUpRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity shrink-0 mt-0.5" />
          </button>
        ))}
      </div>
    </div>
  );
}
