import type { Agency } from "@/shared/types/agency";

import { ConnectionTab } from "./ConnectionTab";
import { GeneralSection } from "./GeneralSection";
import { RoutingTab } from "./RoutingTab";

export function EditTab({ agency }: { agency: Agency }) {
  return (
    <div className="space-y-8">
      <section className="space-y-4">
        <h3 className="text-sm text-foreground">ข้อมูลทั่วไป</h3>
        <GeneralSection agency={agency} />
      </section>
      <section className="space-y-4">
        <h3 className="text-sm text-foreground">การเชื่อมต่อ</h3>
        <ConnectionTab agency={agency} />
      </section>
      <section className="space-y-4">
        <h3 className="text-sm text-foreground">Routing</h3>
        <RoutingTab agency={agency} />
      </section>
    </div>
  );
}
