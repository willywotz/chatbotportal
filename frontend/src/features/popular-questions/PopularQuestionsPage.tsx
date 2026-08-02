import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/shared/components/ui/button";
import { Loader2, Plus, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import {
  createPopularQuestion,
  deletePopularQuestion,
  listPopularQuestions,
  regeneratePopularQuestions,
  updatePopularQuestion,
  type PopularQuestionAdmin,
  type PopularQuestionInput,
  type PopularQuestionUpdate,
} from "@/features/popular-questions/popularQuestionsApi";
import { useAgencies } from "@/features/agencies/useAgencies";
import { PopularQuestionsList } from "./PopularQuestionsList";
import { CreatePopularQuestionDialog } from "./CreatePopularQuestionDialog";
import { EditPopularQuestionDialog } from "./EditPopularQuestionDialog";
import { DeletePopularQuestionDialog } from "./DeletePopularQuestionDialog";

const QUERY_KEY = ["popular-questions"];

export default function PopularQuestionsPage() {
  const queryClient = useQueryClient();

  const { data: questions = [], isLoading } = useQuery({
    queryKey: QUERY_KEY,
    queryFn: listPopularQuestions,
  });

  const { data: agencies = [], isLoading: agenciesLoading } = useAgencies();

  const invalidate = () => queryClient.invalidateQueries({ queryKey: QUERY_KEY });

  // Create
  const [createOpen, setCreateOpen] = useState(false);
  const createMutation = useMutation({
    mutationFn: (input: PopularQuestionInput) => createPopularQuestion(input),
    onSuccess: () => {
      invalidate();
      toast.success("เพิ่มคำถามยอดนิยมเรียบร้อย");
      setCreateOpen(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  // Edit
  const [editTarget, setEditTarget] = useState<PopularQuestionAdmin | null>(null);
  const editMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: PopularQuestionUpdate }) =>
      updatePopularQuestion(id, body),
    onSuccess: () => {
      invalidate();
      toast.success("แก้ไขคำถามยอดนิยมเรียบร้อย");
      setEditTarget(null);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  // Delete
  const [deleteTarget, setDeleteTarget] = useState<PopularQuestionAdmin | null>(null);
  const deleteMutation = useMutation({
    mutationFn: (id: string) => deletePopularQuestion(id),
    onSuccess: () => {
      invalidate();
      toast.success("ลบคำถามยอดนิยมเรียบร้อย");
      setDeleteTarget(null);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  // Pin / hide / reorder — all go through the same PATCH mutation.
  const patchMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: PopularQuestionUpdate }) =>
      updatePopularQuestion(id, body),
    onSuccess: invalidate,
    onError: (e: Error) => toast.error(e.message),
  });

  // Regenerate
  const regenerateMutation = useMutation({
    mutationFn: regeneratePopularQuestions,
    onSuccess: () => {
      toast.success("เริ่มสร้างคำถามยอดนิยมใหม่แล้ว");
      invalidate();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="p-4 md:p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg text-foreground">คำถามยอดนิยม</h2>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => regenerateMutation.mutate()}
            disabled={regenerateMutation.isPending}
          >
            {regenerateMutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-1 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4 mr-1" />
            )}
            สร้างใหม่ตอนนี้
          </Button>
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4 mr-1" />
            เพิ่มคำถาม
          </Button>
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      )}

      {!isLoading && (
        <PopularQuestionsList
          questions={questions}
          onEdit={setEditTarget}
          onDelete={setDeleteTarget}
          onTogglePin={(q) => patchMutation.mutate({ id: q.id, body: { pinned: !q.pinned } })}
          onToggleHidden={(q) => patchMutation.mutate({ id: q.id, body: { hidden: !q.hidden } })}
          onReorder={(q, direction) =>
            patchMutation.mutate({ id: q.id, body: { sort_order: q.sort_order + direction } })
          }
        />
      )}

      <CreatePopularQuestionDialog
        open={createOpen}
        agencies={agencies}
        agenciesLoading={agenciesLoading}
        mutation={createMutation}
        onClose={() => setCreateOpen(false)}
      />

      <EditPopularQuestionDialog
        target={editTarget}
        agencies={agencies}
        agenciesLoading={agenciesLoading}
        mutation={editMutation}
        onClose={() => setEditTarget(null)}
      />

      <DeletePopularQuestionDialog
        target={deleteTarget}
        mutation={deleteMutation}
        onConfirm={() => deleteMutation.mutate(deleteTarget!.id)}
        onClose={() => setDeleteTarget(null)}
      />
    </div>
  );
}
