import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/shared/components/ui/alert-dialog';
import { toast } from 'sonner';
import type { ManagedUser } from './userApi';
import { useDeleteUser } from './useUsers';

interface Props {
  user: ManagedUser | null;
  onOpenChange: (open: boolean) => void;
}

export function DeleteUserDialog({ user, onOpenChange }: Props) {
  const mut = useDeleteUser();

  async function handleConfirm() {
    if (!user) return;
    try {
      await mut.mutateAsync(user.id);
      toast.success('ลบผู้ใช้แล้ว');
      onOpenChange(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'เกิดข้อผิดพลาด');
    }
  }

  return (
    <AlertDialog open={Boolean(user)} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>ลบผู้ใช้?</AlertDialogTitle>
          <AlertDialogDescription>
            {user?.email} — การลบถาวรและกู้คืนไม่ได้
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={mut.isPending}>ยกเลิก</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirm}
            disabled={mut.isPending}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            ลบผู้ใช้
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
