import { ArrowLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";

import {
  agencyToFormState,
  buildSavePayload,
  canActivate,
  DEFAULT_FORM_STATE,
  isGeneralValid,
  parseExpectedPayload,
  type AgencyFormState,
} from "../agencyForm";
import { useAgencies, useCreateAgency, useUpdateAgency, useUpdateAgencyStatus } from "../useAgencies";
import { ConnectionFields } from "./ConnectionFields";
import { GeneralFields } from "./GeneralFields";
import { RoutingFields } from "./RoutingFields";

export default function AgencyFormPage() {
  const { id: routeId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: agencies = [], isLoading } = useAgencies();
  const createMutation = useCreateAgency();
  const updateMutation = useUpdateAgency();
  const statusMutation = useUpdateAgencyStatus();

  const [form, setForm] = useState<AgencyFormState>(DEFAULT_FORM_STATE);
  const [agencyId, setAgencyId] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!routeId || loaded || isLoading) return;
    const agency = agencies.find((a) => a.id === routeId);
    if (agency) {
      setForm(agencyToFormState(agency));
      setAgencyId(agency.id);
      setLoaded(true);
    } else {
      toast.error("ไม่พบหน่วยงาน");
      setLoaded(true);
      navigate("/agencies");
    }
  }, [routeId, agencies, isLoading, loaded, navigate]);

  const saving = createMutation.isPending || updateMutation.isPending || statusMutation.isPending;

  const patch = (p: Partial<AgencyFormState>) => setForm((f) => ({ ...f, ...p }));

  const persistDraft = async (): Promise<string> => {
    const payload = {
      ...buildSavePayload(form, parseExpectedPayload(form.expectedPayload).value),
      status: agencyId ? form.status : ("draft" as const),
    };
    if (agencyId) {
      await updateMutation.mutateAsync({ ...payload, id: agencyId });
      return agencyId;
    }
    const created = await createMutation.mutateAsync(payload);
    setAgencyId(created.id);
    return created.id;
  };

  const save = async (activate: boolean) => {
    try {
      const id = await persistDraft();
      if (activate && form.status !== "active") await statusMutation.mutateAsync({ id, status: "active" });
      toast.success(activate ? "เปิดใช้งานหน่วยงานสำเร็จ" : "บันทึก Draft สำเร็จ");
      navigate(`/agencies/${id}`);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "เกิดข้อผิดพลาด");
    }
  };

  return (
    <div className="p-4 md:p-6">
      <Button variant="ghost" size="sm" onClick={() => navigate("/agencies")} className="mb-4">
        <ArrowLeft className="h-4 w-4 mr-1" /> กลับ
      </Button>

      <div className="space-y-6">
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 md:items-start">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">ข้อมูลทั่วไป</CardTitle>
            </CardHeader>
            <CardContent>
              <GeneralFields form={form} patch={patch} />
            </CardContent>
          </Card>

          <Card className="md:row-span-2">
            <CardHeader>
              <CardTitle className="text-base">การเชื่อมต่อ</CardTitle>
            </CardHeader>
            <CardContent>
              <ConnectionFields form={form} patch={patch} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Routing</CardTitle>
            </CardHeader>
            <CardContent>
              <RoutingFields form={form} patch={patch} />
            </CardContent>
          </Card>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border pt-4">
          <Button variant="outline" onClick={() => save(false)} disabled={!isGeneralValid(form) || saving}>
            บันทึก Draft
          </Button>
          <Button onClick={() => save(true)} disabled={!canActivate(form) || saving}>
            เปิดใช้งาน
          </Button>
        </div>
      </div>
    </div>
  );
}
