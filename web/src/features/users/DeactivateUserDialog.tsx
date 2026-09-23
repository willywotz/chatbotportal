import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/shared/components/ui/alert-dialog';
import { toast } from 'sonner';
import type { ManagedUser } from './userApi';
import { useSetUserActive } from './useUsers';

interface Props {
  user: ManagedUser | null;
  onOpenChange: (open: boolean) => void;
}

export function DeactivateUserDialog({ user, onOpenChange }: Props) {
  const mut = useSetUserActive();
  const willDeactivate = user?.isActive === true;

  async function handleConfirm() {
    if (!user) return;
    try {
      await mut.mutateAsync({ id: user.id, active: !user.isActive });
      toast.success(willDeactivate ? 'ปิดการใช้งานผู้ใช้แล้ว' : 'เปิดการใช้งานผู้ใช้แล้ว');
      onOpenChange(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'เกิดข้อผิดพลาด');
    }
  }

  return (
    <AlertDialog open={Boolean(user)} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {willDeactivate ? 'ปิดการใช้งานผู้ใช้?' : 'เปิดการใช้งานผู้ใช้?'}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {user?.email}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={mut.isPending}>ยกเลิก</AlertDialogCancel>
          <AlertDialogAction onClick={handleConfirm} disabled={mut.isPending}>
            ยืนยัน
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
