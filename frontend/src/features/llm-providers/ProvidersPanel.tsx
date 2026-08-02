import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus } from "lucide-react";
import { toast } from "sonner";

import { CreateLlmProviderDialog } from "./CreateLlmProviderDialog";
import { DeleteLlmProviderDialog } from "./DeleteLlmProviderDialog";
import { EditLlmProviderDialog } from "./EditLlmProviderDialog";
import { LlmProviderList } from "./LlmProviderList";
import {
  createProvider,
  deleteProvider,
  listProviders,
  updateProvider,
  type LlmProvider,
  type LlmProviderInput,
} from "./llmProviderApi";
import { Button } from "@/shared/components/ui/button";

const QUERY_KEY = ["llm-providers"];

export function ProvidersPanel() {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({ queryKey: QUERY_KEY, queryFn: listProviders });
  const providers = data?.data ?? [];

  const [createOpen, setCreateOpen] = useState(false);
  const createMutation = useMutation({
    mutationFn: (input: LlmProviderInput) => createProvider(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
      toast.success("สร้างผู้ให้บริการ LLM เรียบร้อย");
      setCreateOpen(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const [editTarget, setEditTarget] = useState<LlmProvider | null>(null);
  const editMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<LlmProviderInput> }) => updateProvider(id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
      toast.success("แก้ไขผู้ให้บริการ LLM เรียบร้อย");
      setEditTarget(null);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const [deleteTarget, setDeleteTarget] = useState<LlmProvider | null>(null);
  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteProvider(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
      toast.success("ลบผู้ให้บริการ LLM เรียบร้อย");
      setDeleteTarget(null);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg text-foreground">ผู้ให้บริการ LLM</h2>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4 mr-1" />
          เพิ่มผู้ให้บริการ
        </Button>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      )}

      {!isLoading && (
        <LlmProviderList providers={providers} onEdit={setEditTarget} onDelete={setDeleteTarget} />
      )}

      <CreateLlmProviderDialog open={createOpen} mutation={createMutation} onClose={() => setCreateOpen(false)} />
      <EditLlmProviderDialog target={editTarget} mutation={editMutation} onClose={() => setEditTarget(null)} />
      <DeleteLlmProviderDialog
        target={deleteTarget}
        mutation={deleteMutation}
        onConfirm={() => deleteMutation.mutate(deleteTarget!.id)}
        onClose={() => setDeleteTarget(null)}
      />
    </div>
  );
}
