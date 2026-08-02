import { useState } from "react";
import { cn } from "@/shared/lib/utils";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useAgencies } from "@/features/agencies/useAgencies";
import { AgencyLogo } from "@/shared/components/AgencyLogo";
import { PageHeader } from "@/shared/components/layout/PageHeader";

interface NodeData {
  id: string;
  label: string;
  icon: string;
  description: string;
  details: string[];
}

const workflowNodes: NodeData[] = [
  {
    id: "user",
    label: "ผู้ใช้งาน",
    icon: "👤",
    description: "ผู้ใช้ส่งคำถามผ่าน Chat Interface",
    details: ["พิมพ์คำถามภาษาธรรมชาติ", "เลือกคำถามแนะนำ", "รองรับทั้งภาษาไทยและอังกฤษ"],
  },
  {
    id: "gateway",
    label: "API Gateway",
    icon: "🌐",
    description: "จุดรับคำถามและจัดการ routing",
    details: ["Authentication & Authorization", "Request Validation", "Load Balancing"],
  },
  {
    id: "orchestrator",
    label: "AI Orchestrator Agent",
    icon: "🤖",
    description: "วิเคราะห์คำถามและวางแผนการสืบค้น",
    details: ["วิเคราะห์ Intent ของคำถาม", "เลือกหน่วยงานที่เกี่ยวข้อง", "วางแผน query strategy", "จัดลำดับความสำคัญ"],
  },
  {
    id: "search",
    label: "Multi-Agent Search",
    icon: "🔍",
    description: "สืบค้นข้อมูลจากหลายหน่วยงานพร้อมกัน",
    details: ["Parallel query execution", "Timeout management", "Error handling & retry", "Result caching"],
  },
  {
    id: "synthesizer",
    label: "Answer Synthesizer",
    icon: "📝",
    description: "รวบรวมและสังเคราะห์คำตอบ",
    details: ["รวม results จากหลายแหล่ง", "จัดรูปแบบคำตอบ", "เพิ่มแหล่งอ้างอิง", "ตรวจสอบความถูกต้อง"],
  },
];

function WorkflowNode({ node, isExpanded, onToggle }: { node: NodeData; isExpanded: boolean; onToggle: () => void }) {
  return (
    <div
      className={cn(
        "bg-card border border-border rounded-xl p-4 cursor-pointer transition-all duration-200 hover:shadow-md hover:border-primary/40",
        isExpanded && "ring-2 ring-primary/20"
      )}
      onClick={onToggle}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-2xl">{node.icon}</span>
          <div>
            <h3 className="text-sm text-foreground">{node.label}</h3>
            <p className="text-xs text-muted-foreground">{node.description}</p>
          </div>
        </div>
        {isExpanded ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
      </div>
      {isExpanded && (
        <div className="mt-3 pt-3 border-t border-border animate-fade-in">
          <ul className="space-y-1.5">
            {node.details.map((d, i) => (
              <li key={i} className="text-xs text-muted-foreground flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-primary shrink-0" />
                {d}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ArrowDown() {
  return (
    <div className="flex justify-center py-1">
      <div className="w-0.5 h-6 bg-border relative">
        <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-0 h-0 border-l-[5px] border-r-[5px] border-t-[6px] border-l-transparent border-r-transparent border-t-border" />
      </div>
    </div>
  );
}

export default function ArchitecturePage() {
  const [expandedNode, setExpandedNode] = useState<string | null>(null);
  const { data: agencies = [], isLoading } = useAgencies();

  const toggle = (id: string) => setExpandedNode(prev => prev === id ? null : id);

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <PageHeader
        title="System Architecture"
        subtitle="แผนผังระบบ Agentic AI — คลิกแต่ละ node เพื่อดูรายละเอียด"
      />

      {/* Main workflow */}
      <div className="max-w-md mx-auto">
        {workflowNodes.map((node, i) => (
          <div key={node.id}>
            <WorkflowNode node={node} isExpanded={expandedNode === node.id} onToggle={() => toggle(node.id)} />
            {i < workflowNodes.length - 1 && <ArrowDown />}
          </div>
        ))}
      </div>

      {/* Agency connections */}
      <div>
        <h2 className="text-base text-foreground mb-3">หน่วยงานที่เชื่อมต่อ</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {agencies.map((a) => (
            <div key={a.id} className="bg-card border border-border rounded-xl p-4 space-y-2">
              <div className="flex items-center gap-2">
                <AgencyLogo logo={a.logo} alt={a.shortName} className="text-xl w-6 h-6 rounded object-cover" />
                <span className="font-medium text-sm text-foreground">{a.shortName}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className={cn(
                  "text-[10px] font-medium px-2 py-0.5 rounded-full",
                  a.connectionType === 'MCP' && "bg-primary/10 text-primary",
                  a.connectionType === 'API' && "bg-success/10 text-success",
                  a.connectionType === 'A2A' && "bg-warning/10 text-warning",
                )}>{a.connectionType}</span>
                <span className="w-2 h-2 rounded-full bg-green-500" />
                <span className="text-[10px] text-muted-foreground">Active</span>
              </div>
              <p className="text-[10px] text-muted-foreground leading-relaxed">{a.description}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
