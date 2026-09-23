import { useLayoutEffect, useRef } from 'react';
import { ArrowUp, Square } from 'lucide-react';
import { Button } from '@/shared/components/ui/button';

interface ChatInputProps {
  input: string;
  setInput: (value: string) => void;
  isTyping: boolean;
  onSend: () => void;
  onCancel: () => void;
}

export function ChatInput({ input, setInput, isTyping, onSend, onCancel }: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-grow the textarea up to its max height, then let it scroll.
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [input]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (input.trim()) onSend();
    }
  };

  return (
    <div className="p-4">
      <div className="max-w-3xl mx-auto">
        <div className="flex flex-col rounded-3xl border border-input bg-white shadow-sm transition-shadow focus-within:shadow-md">
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="พิมพ์คำถามของคุณที่นี่..."
            className="resize-none bg-transparent px-4 pt-3.5 pb-1 text-sm leading-6 max-h-48 focus:outline-none placeholder:text-muted-foreground" />
          <div className="flex items-center justify-end px-2.5 pb-2.5">
            {isTyping ? (
              <Button onClick={onCancel} size="icon" className="h-8 w-8 rounded-full" title="ยกเลิก">
                <Square className="h-3.5 w-3.5 fill-current" />
              </Button>
            ) : (
              <Button onClick={onSend} size="icon" className="h-8 w-8 rounded-full" disabled={!input.trim()} title="ส่ง">
                <ArrowUp className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
