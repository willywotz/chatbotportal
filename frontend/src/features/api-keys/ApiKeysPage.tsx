import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/shared/components/ui/button";
import { PageHeader } from "@/shared/components/layout/PageHeader";
import { Loader2, Plus } from "lucide-react";
import { toast } from "sonner";
import {
  listAPIKeys,
  createAPIKey,
  updateAPIKey,
  revokeAPIKey,
  deleteAPIKey,
  type APIKey,
  type CreatedAPIKey,
} from "@/features/api-keys/apiKeyApi";
import { ApiKeyList } from "./ApiKeyList";
import { CreateApiKeyDialog } from "./CreateApiKeyDialog";
import { RevealKeyDialog } from "./RevealKeyDialog";
import { EditApiKeyDialog } from "./EditApiKeyDialog";
import { DeleteApiKeyDialog } from "./DeleteApiKeyDialog";

export default function ApiKeysPage() {
  const queryClient = useQueryClient();

  const { data: keys = [], isLoading } = useQuery({
    queryKey: ["apiKeys"],
    queryFn: listAPIKeys,
  });

  // Create
  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createExpiresInDays, setCreateExpiresInDays] = useState("");
  const [newKey, setNewKey] = useState<CreatedAPIKey | null>(null);
  const resetCreateForm = useCallback(() => {
    setCreateName("");
    setCreateExpiresInDays("");
  }, []);
  const createMutation = useMutation({
    mutationFn: () => {
      const expiresInDays = createExpiresInDays.trim();
      return createAPIKey({
        name: createName.trim(),
        ...(expiresInDays ? { expires_in_days: Number(expiresInDays) } : {}),
      });
    },
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ["apiKeys"] });
      setCreateOpen(false);
      resetCreateForm();
      setNewKey(created);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  // Revoke
  const revokeMutation = useMutation({
    mutationFn: (id: string) => revokeAPIKey(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["apiKeys"] });
      toast.success("เพิกถอน API Key เรียบร้อย");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const handleRevoke = useCallback(
    (key: APIKey) => {
      if (window.confirm("เพิกถอนคีย์นี้? คีย์จะใช้งานไม่ได้อีกต่อไป")) {
        revokeMutation.mutate(key.id);
      }
    },
    [revokeMutation],
  );

  // Edit
  const [editTarget, setEditTarget] = useState<APIKey | null>(null);
  const [editName, setEditName] = useState("");
  const editMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => updateAPIKey(id, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["apiKeys"] });
      toast.success("แก้ไขชื่อเรียบร้อย");
      setEditTarget(null);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const openEdit = useCallback((key: APIKey) => {
    setEditTarget(key);
    setEditName(key.name);
  }, []);

  // Delete
  const [deleteTarget, setDeleteTarget] = useState<APIKey | null>(null);
  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteAPIKey(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["apiKeys"] });
      toast.success("ลบ API Key เรียบร้อย");
      setDeleteTarget(null);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="p-4 md:p-6 space-y-4">
      <PageHeader
        title="API Keys"
        actions={
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4 mr-1" />
            สร้าง API Key
          </Button>
        }
      />

      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      )}

      {!isLoading && (
        <ApiKeyList
          keys={keys}
          revokePending={revokeMutation.isPending}
          onEdit={openEdit}
          onRevoke={handleRevoke}
          onDelete={setDeleteTarget}
        />
      )}

      <CreateApiKeyDialog
        open={createOpen}
        name={createName}
        expiresInDays={createExpiresInDays}
        mutation={createMutation}
        onNameChange={setCreateName}
        onExpiresInDaysChange={setCreateExpiresInDays}
        onClose={() => { setCreateOpen(false); resetCreateForm(); }}
      />

      <RevealKeyDialog
        newKey={newKey}
        onClose={() => setNewKey(null)}
      />

      <EditApiKeyDialog
        target={editTarget}
        name={editName}
        mutation={editMutation}
        onNameChange={setEditName}
        onSave={() => editMutation.mutate({ id: editTarget!.id, name: editName.trim() })}
        onClose={() => setEditTarget(null)}
      />

      <DeleteApiKeyDialog
        target={deleteTarget}
        mutation={deleteMutation}
        onConfirm={() => deleteMutation.mutate(deleteTarget!.id)}
        onClose={() => setDeleteTarget(null)}
      />
    </div>
  );
}
