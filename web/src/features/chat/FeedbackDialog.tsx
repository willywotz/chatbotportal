import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/shared/components/ui/dialog";
import { Button } from "@/shared/components/ui/button";
import { Textarea } from "@/shared/components/ui/textarea";

interface FeedbackDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (text: string) => void;
}

export function FeedbackDialog({ open, onClose, onSubmit }: FeedbackDialogProps) {
  const [text, setText] = useState("");

  const handleSubmit = () => {
    onSubmit(text.trim());
    setText("");
    onClose();
  };

  const handleSkip = () => {
    onSubmit("");
    setText("");
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-base">ขอบคุณสำหรับ Feedback</DialogTitle>
          <DialogDescription>
            กรุณาบอกเหตุผลเพิ่มเติม เพื่อช่วยให้เราปรับปรุงระบบ (ไม่บังคับ)
          </DialogDescription>
        </DialogHeader>
        <Textarea
          placeholder="เช่น คำตอบไม่ตรงประเด็น, ข้อมูลไม่ถูกต้อง..."
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
          maxLength={500}
        />
        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="ghost" size="sm" onClick={handleSkip}>
            ข้าม
          </Button>
          <Button size="sm" onClick={handleSubmit}>
            ส่ง Feedback
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
