import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { EditLlmBindingDialog } from "./EditLlmBindingDialog";
import { LlmBindingsList, type BindingTestState } from "./LlmBindingsList";
import {
  listBindings,
  testBinding,
  updateBinding,
  type LlmBinding,
  type LlmBindingInput,
} from "./llmBindingApi";
import { listProviders } from "@/features/llm-providers/llmProviderApi";

const QUERY_KEY = ["llm-bindings"];

export function BindingsPanel() {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({ queryKey: QUERY_KEY, queryFn: listBindings });
  const bindings = data?.data ?? [];

  const { data: providersData, isLoading: providersLoading } = useQuery({
    queryKey: ["llm-providers"],
    queryFn: listProviders,
  });
  const providers = providersData?.data ?? [];

  const [editTarget, setEditTarget] = useState<LlmBinding | null>(null);
  const editMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<LlmBindingInput> }) => updateBinding(id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
      toast.success("แก้ไขการผูก LLM เรียบร้อย");
      setEditTarget(null);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const [testState, setTestState] = useState<Record<string, BindingTestState>>({});
  const anyTesting = Object.values(testState).some((t) => t.loading);

  const runTest = async (purpose: string) => {
    setTestState((s) => ({ ...s, [purpose]: { loading: true, result: s[purpose]?.result } }));
    try {
      const result = await testBinding(purpose);
      setTestState((s) => ({ ...s, [purpose]: { loading: false, result } }));
    } catch (e) {
      setTestState((s) => ({
        ...s,
        [purpose]: { loading: false, result: { ok: false, latency_ms: 0, model: null, error: (e as Error).message } },
      }));
    }
  };

  const runAll = () => bindings.forEach((b) => runTest(b.purpose));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg text-foreground">การผูก LLM</h2>
        <button
          onClick={runAll}
          disabled={bindings.length === 0 || anyTesting}
          className="flex items-center gap-1.5 rounded border px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-foreground transition-colors disabled:opacity-50"
        >
          {anyTesting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          ทดสอบทั้งหมด
        </button>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      )}

      {!isLoading && (
        <LlmBindingsList bindings={bindings} onEdit={setEditTarget} onTest={runTest} testState={testState} />
      )}

      <EditLlmBindingDialog
        target={editTarget}
        bindings={bindings}
        providers={providers}
        providersLoading={providersLoading}
        mutation={editMutation}
        onClose={() => setEditTarget(null)}
      />
    </div>
  );
}
