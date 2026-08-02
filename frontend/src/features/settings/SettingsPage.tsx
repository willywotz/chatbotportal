import { useState, useEffect, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { PageHeader } from "@/shared/components/layout/PageHeader";
import { Button } from "@/shared/components/ui/button";
import { Label } from "@/shared/components/ui/label";
import { Alert, AlertDescription } from "@/shared/components/ui/alert";
import { Loader2, Save, RotateCcw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/features/auth/useAuth";
import { Navigate } from "react-router-dom";
import { flushCache, getSettings, updateSettings } from "@/features/settings/settingsApi";
import { FieldInput } from "@/shared/components/FieldInput";

const RESTART_FIELDS = new Set(["DATABASE_URL", "CORS_ORIGINS", "JWT_SECRET", "JWT_ALGORITHM"]);

export default function SettingsPage() {
  const { isAdmin } = useAuth();
  const queryClient = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
  });

  const [edited, setEdited] = useState<Record<string, string>>({});
  const [original, setOriginal] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!data) return;
    const orig: Record<string, string> = {};
    for (const g of data.groups) {
      for (const f of g.fields) {
        orig[f.key] = f.value;
      }
    }
    setOriginal(orig);
    setEdited(orig);
  }, [data]);

  const dirtyKeys = Object.keys(edited).filter((k) => edited[k] !== original[k]);

  const saveMutation = useMutation({
    mutationFn: () => {
      const updates = dirtyKeys.map((key) => ({ key, value: edited[key] }));
      return updateSettings(updates);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      toast.success("ตั้งค่าเรียบร้อย");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const flushMutation = useMutation({
    mutationFn: flushCache,
    onSuccess: () => toast.success("ล้าง answer cache เรียบร้อย"),
    onError: (e: Error) => toast.error(e.message),
  });

  const handleFlush = () => {
    if (!window.confirm("ล้าง answer cache ทั้งหมด? คำถามที่คล้ายกันจะไม่ถูก cache จนกว่าจะมีคำตอบใหม่")) return;
    flushMutation.mutate();
  };

  const handleChange = useCallback((key: string, value: string) => {
    setEdited((prev) => ({ ...prev, [key]: value }));
  }, []);

  const handleReset = useCallback((key: string, defaultValue: string) => {
    setEdited((prev) => ({ ...prev, [key]: defaultValue }));
  }, []);

  if (!isAdmin) return <Navigate to="/chat" replace />;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="p-6 max-w-4xl mx-auto">
        <Alert variant="destructive">
          <AlertDescription>โหลดการตั้งค่าไม่สำเร็จ กรุณาลองใหม่อีกครั้ง</AlertDescription>
        </Alert>
      </div>
    );
  }

  const groups = data?.groups ?? [];

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <PageHeader
        title="ตั้งค่าระบบ"
        actions={
          <div className="flex gap-2">
            <Button
              variant="outline"
              disabled={flushMutation.isPending}
              onClick={handleFlush}
            >
              {flushMutation.isPending
                ? <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                : <Trash2 className="h-4 w-4 mr-2" />}
              ล้าง answer cache
            </Button>
            <Button
              disabled={dirtyKeys.length === 0 || saveMutation.isPending}
              onClick={() => saveMutation.mutate()}
            >
              {saveMutation.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              <Save className="h-4 w-4 mr-2" />
              บันทึก ({dirtyKeys.length})
            </Button>
          </div>
        }
      />

      {groups.map((group) => (
        <Card key={group.group}>
          <CardHeader>
            <CardTitle className="text-lg">{group.group}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {group.fields.map((field) => (
              <div key={field.key} className="grid grid-cols-[200px_1fr_auto] gap-3 items-start">
                <Label className="text-sm font-mono pt-2">{field.key}</Label>
                <div className="space-y-1">
                  <FieldInput
                    field={field}
                    value={edited[field.key] ?? field.value}
                    onChange={(v) => handleChange(field.key, v)}
                  />
                  {RESTART_FIELDS.has(field.key) && (
                    <Alert variant="destructive" className="py-1.5 px-3">
                      <AlertDescription className="text-xs">
                        เปลี่ยนค่านี้แล้วต้อง restart server ถึงจะมีผล
                      </AlertDescription>
                    </Alert>
                  )}
                  {field.is_secret && (
                    <p className="text-[10px] text-muted-foreground">เว้นว่าง = ไม่เปลี่ยนแปลง</p>
                  )}
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  title="รีเซ็ตเป็นค่าเริ่มต้น"
                  onClick={() => handleReset(field.key, field.default_value)}
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}