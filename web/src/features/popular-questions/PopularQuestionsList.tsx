import { ArrowDown, ArrowUp, Eye, EyeOff, Pencil, Pin, Trash2 } from "lucide-react";
import { AgencyLogo } from "@/shared/components/AgencyLogo";
import { Badge } from "@/shared/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { cn } from "@/shared/lib/utils";
import type { PopularQuestionAdmin, PopularQuestionSource } from "./popularQuestionsApi";

const SOURCE_LABEL: Record<PopularQuestionSource, string> = {
  seed: "ตั้งต้น",
  auto: "อัตโนมัติ",
  manual: "กำหนดเอง",
};

const SOURCE_VARIANT: Record<PopularQuestionSource, "secondary" | "default" | "outline"> = {
  seed: "outline",
  auto: "secondary",
  manual: "default",
};

interface Props {
  questions: PopularQuestionAdmin[];
  onEdit: (question: PopularQuestionAdmin) => void;
  onDelete: (question: PopularQuestionAdmin) => void;
  onTogglePin: (question: PopularQuestionAdmin) => void;
  onToggleHidden: (question: PopularQuestionAdmin) => void;
  onReorder: (question: PopularQuestionAdmin, direction: -1 | 1) => void;
}

export function PopularQuestionsList({
  questions, onEdit, onDelete, onTogglePin, onToggleHidden, onReorder,
}: Props) {
  if (questions.length === 0) {
    return (
      <p className="text-center text-sm text-muted-foreground py-12">
        ยังไม่มีคำถามยอดนิยม กรุณาเพิ่มใหม่
      </p>
    );
  }

  return (
    <div className="border rounded-lg overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>คำถาม</TableHead>
            <TableHead>หน่วยงาน</TableHead>
            <TableHead>ที่มา</TableHead>
            <TableHead className="text-right">คะแนน</TableHead>
            <TableHead>ปักหมุด</TableHead>
            <TableHead>สถานะ</TableHead>
            <TableHead>ลำดับ</TableHead>
            <TableHead className="text-right">การจัดการ</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {questions.map((q) => (
            <TableRow key={q.id}>
              <TableCell className="max-w-[280px] truncate" title={q.text}>{q.text}</TableCell>
              <TableCell className="whitespace-nowrap text-sm">
                {q.agency ? (
                  <span className="flex items-center gap-1">
                    {q.agency.logo && (
                      <AgencyLogo logo={q.agency.logo} alt={q.agency.name} className="w-4 h-4 rounded" />
                    )}
                    <span>{q.agency.name}</span>
                  </span>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </TableCell>
              <TableCell>
                <Badge variant={SOURCE_VARIANT[q.source]}>{SOURCE_LABEL[q.source]}</Badge>
              </TableCell>
              <TableCell className="text-right tabular-nums">{q.score ?? "—"}</TableCell>
              <TableCell>
                <button
                  onClick={() => onTogglePin(q)}
                  aria-label={q.pinned ? "เลิกปักหมุด" : "ปักหมุด"}
                  aria-pressed={q.pinned}
                  className={cn(
                    "p-1.5 rounded hover:bg-accent transition-colors",
                    q.pinned ? "text-primary" : "text-muted-foreground",
                  )}
                >
                  <Pin className="h-3.5 w-3.5" fill={q.pinned ? "currentColor" : "none"} />
                </button>
              </TableCell>
              <TableCell>
                <button
                  onClick={() => onToggleHidden(q)}
                  aria-label={q.hidden ? "แสดง" : "ซ่อน"}
                  className="p-1.5 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1"
                >
                  {q.hidden ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                  <span className="text-xs">{q.hidden ? "ซ่อนอยู่" : "แสดงอยู่"}</span>
                </button>
              </TableCell>
              <TableCell>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => onReorder(q, -1)}
                    aria-label="เลื่อนขึ้น"
                    className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <ArrowUp className="h-3.5 w-3.5" />
                  </button>
                  <span className="text-xs tabular-nums w-4 text-center">{q.sort_order}</span>
                  <button
                    onClick={() => onReorder(q, 1)}
                    aria-label="เลื่อนลง"
                    className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <ArrowDown className="h-3.5 w-3.5" />
                  </button>
                </div>
              </TableCell>
              <TableCell className="text-right">
                <div className="flex items-center justify-end gap-1">
                  <button
                    onClick={() => onEdit(q)}
                    className="p-1.5 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
                    aria-label="แก้ไข"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={() => onDelete(q)}
                    className="p-1.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                    aria-label="ลบ"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
