import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog';
import { Badge } from '@/shared/components/ui/badge';
import { Loader2 } from 'lucide-react';
import { useConversationMessages } from '@/features/history/useConversationMessages';
import type { HistoryItem } from '@/features/history/historyApi';
import { MessageItem } from './MessageItem';

interface ConversationDetailDialogProps {
  conversation: HistoryItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ConversationDetailDialog({ conversation, open, onOpenChange }: ConversationDetailDialogProps) {
  const { data: messages = [], isLoading } = useConversationMessages(
    open ? conversation?.id ?? null : null
  );

  if (!conversation) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="text-base font-semibold">{conversation.title}</DialogTitle>
          <div className="flex items-center gap-2 flex-wrap pt-1">
            {conversation.agencies.map((a, i) => (
              <Badge key={i} variant="outline" className="text-[10px]">{a}</Badge>
            ))}
            {conversation.responseTime && (
              <span className="text-[10px] text-muted-foreground">⏱ {conversation.responseTime}</span>
            )}
            <span className="text-[10px] text-muted-foreground">{conversation.date}</span>
          </div>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto space-y-3 pr-1">
          {isLoading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-5 w-5 animate-spin text-primary" />
            </div>
          )}

          {!isLoading && messages.length === 0 && (
            <p className="text-center text-sm text-muted-foreground py-8">
              ไม่มีข้อความในสนทนานี้
            </p>
          )}

          {!isLoading && messages.map((msg) => <MessageItem key={msg.id} msg={msg} />)}

        </div>
      </DialogContent>
    </Dialog>
  );
}
