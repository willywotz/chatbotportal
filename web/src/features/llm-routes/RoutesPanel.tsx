import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { EditLlmRouteDialog } from "./EditLlmRouteDialog";
import { LlmRoutesList, type RouteTestState } from "./LlmRoutesList";
import { listRoutes, testRoute, updateRoute, type LlmRoute, type LlmRouteInput } from "./llmRouteApi";
import { listProviders } from "@/features/llm-providers/llmProviderApi";

const QUERY_KEY = ["llm-routes"];

export function RoutesPanel() {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({ queryKey: QUERY_KEY, queryFn: listRoutes });
  const routes = data?.data ?? [];

  const { data: providersData, isLoading: providersLoading } = useQuery({
    queryKey: ["llm-providers"],
    queryFn: listProviders,
  });
  const providers = providersData?.data ?? [];

  const [editTarget, setEditTarget] = useState<LlmRoute | null>(null);
  const editMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<LlmRouteInput> }) => updateRoute(id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
      toast.success("แก้ไขเส้นทาง LLM เรียบร้อย");
      setEditTarget(null);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const [testState, setTestState] = useState<Record<string, RouteTestState>>({});
  const anyTesting = Object.values(testState).some((t) => t.loading);

  const runTest = async (purpose: string) => {
    setTestState((s) => ({ ...s, [purpose]: { loading: true, result: s[purpose]?.result } }));
    try {
      const result = await testRoute(purpose);
      setTestState((s) => ({ ...s, [purpose]: { loading: false, result } }));
    } catch (e) {
      setTestState((s) => ({
        ...s,
        [purpose]: { loading: false, result: { ok: false, latency_ms: 0, model: null, error: (e as Error).message } },
      }));
    }
  };

  const runAll = () => routes.forEach((r) => runTest(r.purpose));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg text-foreground">เส้นทาง LLM</h2>
        <button
          onClick={runAll}
          disabled={routes.length === 0 || anyTesting}
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
        <LlmRoutesList routes={routes} onEdit={setEditTarget} onTest={runTest} testState={testState} />
      )}

      <EditLlmRouteDialog
        target={editTarget}
        providers={providers}
        providersLoading={providersLoading}
        mutation={editMutation}
        onClose={() => setEditTarget(null)}
      />
    </div>
  );
}
