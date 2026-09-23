import { Loader2 } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/shared/components/ui/alert-dialog";
import type { UseMutationResult } from "@tanstack/react-query";
import type { PopularQuestionAdmin } from "./popularQuestionsApi";

interface Props {
  target: PopularQuestionAdmin | null;
  mutation: UseMutationResult<unknown, Error, string>;
  onConfirm: () => void;
  onClose: () => void;
}

export function DeletePopularQuestionDialog({ target, mutation, onConfirm, onClose }: Props) {
  return (
    <AlertDialog open={!!target} onOpenChange={(o) => { if (!o) onClose(); }}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>ยืนยันการลบ</AlertDialogTitle>
          <AlertDialogDescription>
            ลบคำถาม "{target?.text}" หรือไม่? ไม่สามารถย้อนกลับได้
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={mutation.isPending}>ยกเลิก</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            disabled={mutation.isPending}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {mutation.isPending && <Loader2 className="h-4 w-4 animate-spin mr-1" />}
            ลบ
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
