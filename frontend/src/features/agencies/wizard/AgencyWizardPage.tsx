import { ArrowLeft, Check } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/shared/components/ui/button";

import {
  agencyToFormState,
  buildSavePayload,
  canActivate,
  DEFAULT_FORM_STATE,
  firstIncompleteStep,
  isStepConnectionValid,
  isStepGeneralValid,
  parseExpectedPayload,
  WIZARD_STEPS,
  type AgencyFormState,
  type WizardStepId,
} from "../agencyForm";
import { useAgencies, useCreateAgency, useUpdateAgency, useUpdateAgencyStatus } from "../useAgencies";
import { StepConnection } from "./StepConnection";
import { StepGeneral } from "./StepGeneral";
import { StepReview } from "./StepReview";
import { StepRouting } from "./StepRouting";
import { StepTest } from "./StepTest";

function stepIndex(id: WizardStepId): number {
  return WIZARD_STEPS.findIndex((s) => s.id === id);
}

export default function AgencyWizardPage() {
  const { id: routeId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: agencies = [], isLoading } = useAgencies();
  const createMutation = useCreateAgency();
  const updateMutation = useUpdateAgency();
  const statusMutation = useUpdateAgencyStatus();

  const [form, setForm] = useState<AgencyFormState>(DEFAULT_FORM_STATE);
  const [step, setStep] = useState<WizardStepId>("general");
  const [agencyId, setAgencyId] = useState<string | null>(null);
  const [conformancePassed, setConformancePassed] = useState(false);
  const [loaded, setLoaded] = useState(false);

  // Resume mode: hydrate form from the existing draft, jump to first incomplete step.
  useEffect(() => {
    if (!routeId || loaded || isLoading) return;
    const agency = agencies.find((a) => a.id === routeId);
    if (agency) {
      const state = agencyToFormState(agency);
      setForm(state);
      setStep(firstIncompleteStep(state));
      setAgencyId(agency.id);
      setConformancePassed(Boolean(agency.conformanceReport?.passed));
      setLoaded(true);
    } else {
      toast.error("ไม่พบหน่วยงาน");
      setLoaded(true);
      navigate("/agencies");
    }
  }, [routeId, agencies, isLoading, loaded, navigate]);

  const saving = createMutation.isPending || updateMutation.isPending || statusMutation.isPending;

  const patch = (p: Partial<AgencyFormState>) => setForm((f) => ({ ...f, ...p }));

  const stepValid: Record<WizardStepId, boolean> = {
    general: isStepGeneralValid(form),
    connection: isStepConnectionValid(form),
    test: true,
    routing: true,
    review: true,
  };

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

  const goNext = async () => {
    const idx = stepIndex(step);
    // Leaving the connection step persists the draft so the test step has an id.
    if (step === "connection") {
      try {
        await persistDraft();
      } catch (err: unknown) {
        toast.error(err instanceof Error ? err.message : "เกิดข้อผิดพลาด");
        return;
      }
    }
    setStep(WIZARD_STEPS[idx + 1].id);
  };

  const goBack = () => {
    const idx = stepIndex(step);
    if (idx === 0) navigate("/agencies");
    else setStep(WIZARD_STEPS[idx - 1].id);
  };

  const finish = async (activate: boolean) => {
    try {
      const id = await persistDraft();
      if (activate && form.status !== "active") await statusMutation.mutateAsync({ id, status: "active" });
      toast.success(activate ? "เปิดใช้งานหน่วยงานสำเร็จ" : "บันทึกเป็น Draft สำเร็จ");
      navigate(`/agencies/${id}`);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "เกิดข้อผิดพลาด");
    }
  };

  const saveDraftAndExit = async () => {
    try {
      const id = await persistDraft();
      toast.success("บันทึก Draft สำเร็จ");
      navigate(`/agencies/${id}`);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "เกิดข้อผิดพลาด");
    }
  };

  const currentIdx = stepIndex(step);

  return (
    <div className="p-4 md:p-6">
      <Button variant="ghost" size="sm" onClick={() => navigate("/agencies")} className="mb-4">
        <ArrowLeft className="h-4 w-4 mr-1" /> กลับ
      </Button>
      <div className="flex gap-8">
        <nav className="w-48 shrink-0 space-y-1">
          {WIZARD_STEPS.map((s, i) => (
            <div
              key={s.id}
              className={`flex items-center gap-2 text-sm rounded-md px-3 py-2 ${
                s.id === step
                  ? "bg-accent font-medium text-foreground"
                  : i < currentIdx
                    ? "text-foreground"
                    : "text-muted-foreground"
              }`}
            >
              {i < currentIdx ? (
                <Check className="h-3.5 w-3.5 text-green-600" />
              ) : (
                <span className="w-3.5 text-center text-xs">{i + 1}</span>
              )}
              {s.label}
            </div>
          ))}
        </nav>

        <div className="flex-1 min-w-0">
          {step === "general" && <StepGeneral form={form} patch={patch} />}
          {step === "connection" && <StepConnection form={form} patch={patch} />}
          {step === "test" && agencyId && <StepTest agencyId={agencyId} onResult={setConformancePassed} />}
          {step === "routing" && <StepRouting form={form} patch={patch} />}
          {step === "review" && <StepReview form={form} />}
          {step === "review" && !conformancePassed && (
            <p className="text-sm text-amber-600 mt-2">
              ต้องรันชุดทดสอบ Conformance ให้ผ่านในขั้นตอน “ทดสอบ” ก่อนจึงจะเปิดใช้งานได้
            </p>
          )}

          <div className="flex items-center justify-between mt-8 max-w-lg">
            <Button variant="ghost" onClick={goBack}>
              ย้อนกลับ
            </Button>
            <div className="flex gap-2">
              {currentIdx >= stepIndex("connection") && step !== "review" && (
                <Button variant="outline" onClick={saveDraftAndExit} disabled={!stepValid.general || saving}>
                  บันทึก Draft
                </Button>
              )}
              {step !== "review" && (
                <Button onClick={goNext} disabled={!stepValid[step] || saving}>
                  ถัดไป
                </Button>
              )}
              {step === "review" && (
                <>
                  <Button variant="outline" onClick={() => finish(false)} disabled={saving}>
                    บันทึกเป็น Draft
                  </Button>
                  <Button onClick={() => finish(true)} disabled={!canActivate(form) || !conformancePassed || saving}>
                    เปิดใช้งาน
                  </Button>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
