import { ProvidersPanel } from "@/features/llm-providers/ProvidersPanel";
import { RoutesPanel } from "@/features/llm-routes/RoutesPanel";

export default function LlmSettingsPage() {
  return (
    <div className="p-4 md:p-6 grid grid-cols-1 md:grid-cols-2 gap-6">
      <ProvidersPanel />
      <RoutesPanel />
    </div>
  );
}
