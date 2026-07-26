import type { ConversationMessage } from "@/shared/types";
import { AssistantMessageContent } from "@/shared/components/AssistantMessageContent";
import { toAgentStepsSnapshot } from "@/shared/lib/agentSteps";

export function MessageItem({ msg }: { msg: ConversationMessage }) {
  const isUser = msg.role === 'user';

  return (
    <div className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {/* {!isUser && (
        <div className="shrink-0 w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center">
          <Bot className="h-4 w-4 text-primary" />
        </div>
      )} */}

      {isUser ? (
        <div className="rounded-lg px-3 py-2 max-w-[80%] text-sm bg-primary text-primary-foreground">
          <p className="whitespace-pre-wrap">{msg.content}</p>
        </div>
      ) : (
        <div className="max-w-[80%] space-y-2">
          <AssistantMessageContent
            content={msg.content}
            summary={msg.summary}
            references={msg.summary_references}
            steps={toAgentStepsSnapshot(msg.agent_steps)}
          />
        </div>
      )}

      {/* {isUser && (
        <div className="shrink-0 w-7 h-7 rounded-full bg-primary flex items-center justify-center">
          <User className="h-4 w-4 text-primary-foreground" />
        </div>
      )} */}
    </div>
  );
}
