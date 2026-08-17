import { useEffect, useState } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/shared/components/ui/dialog';
import { Button } from '@/shared/components/ui/button';
import { Label } from '@/shared/components/ui/label';
import { PasswordInput } from '@/shared/components/ui/password-input';
import { toast } from 'sonner';
import { api } from '@/shared/lib/apiClient';
import { validateChangePassword } from './changePassword';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ChangePasswordDialog({ open, onOpenChange }: Props) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (open) {
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    }
  }, [open]);

  async function handleSubmit() {
    const err = validateChangePassword({ currentPassword, newPassword, confirmPassword });
    if (err) { toast.error(err); return; }
    setPending(true);
    try {
      await api.post('/api/v1/authentication/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
      });
      toast.success('เปลี่ยนรหัสผ่านสำเร็จ');
      onOpenChange(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'เกิดข้อผิดพลาด');
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>เปลี่ยนรหัสผ่าน</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="currentPassword">รหัสผ่านปัจจุบัน</Label>
            <PasswordInput id="currentPassword" autoComplete="current-password"
              value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="newPassword">รหัสผ่านใหม่</Label>
            <PasswordInput id="newPassword" autoComplete="new-password"
              value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="confirmPassword">ยืนยันรหัสผ่านใหม่</Label>
            <PasswordInput id="confirmPassword" autoComplete="new-password"
              value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>ยกเลิก</Button>
          <Button onClick={handleSubmit} disabled={pending}>บันทึก</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
