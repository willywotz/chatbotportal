import { Plus, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";

interface Props {
  scope: string[];
  onChange: (scope: string[]) => void;
}

export function DataScopeEditor({ scope, onChange }: Props) {
  const [input, setInput] = useState("");

  const add = () => {
    const value = input.trim();
    if (value && !scope.includes(value)) onChange([...scope, value]);
    setInput("");
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1">
        {scope.map((s) => (
          <span
            key={s}
            className="inline-flex items-center gap-1 text-xs bg-accent text-accent-foreground px-2 py-0.5 rounded-full"
          >
            {s}
            <button type="button" onClick={() => onChange(scope.filter((x) => x !== s))} aria-label={`ลบ ${s}`}>
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <Input
          placeholder="เพิ่มขอบเขตข้อมูล เช่น ภาษี"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
        />
        <Button type="button" variant="outline" size="icon" onClick={add} aria-label="เพิ่มขอบเขต">
          <Plus className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
