import { useState } from 'react';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/shared/components/ui/table';
import { Button } from '@/shared/components/ui/button';
import { PageHeader } from '@/shared/components/layout/PageHeader';
import { Input } from '@/shared/components/ui/input';
import { Badge } from '@/shared/components/ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/shared/components/ui/select';
import { UserPlus } from 'lucide-react';
import { useUsers } from './useUsers';
import type { ManagedUser, UserRole } from './userApi';
import { ROLE_LABEL, ROLE_ORDER } from './roleLabels';
import { UserFormDialog } from './UserFormDialog';
import { DeactivateUserDialog } from './DeactivateUserDialog';

export default function UsersPage() {
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<UserRole | 'all'>('all');
  const { data: users = [], isLoading, isError } = useUsers({
    search: search || undefined,
    role: roleFilter === 'all' ? undefined : roleFilter,
    status: 'all',
  });
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<ManagedUser | null>(null);
  const [toggling, setToggling] = useState<ManagedUser | null>(null);

  function openCreate() { setEditing(null); setFormOpen(true); }
  function openEdit(u: ManagedUser) { setEditing(u); setFormOpen(true); }

  return (
    <div className="p-6 space-y-4">
      <PageHeader
        title="จัดการผู้ใช้"
        actions={<Button onClick={openCreate}><UserPlus className="h-4 w-4 mr-2" />เพิ่มผู้ใช้</Button>}
      />

      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="ค้นหาอีเมลหรือชื่อ..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-sm"
        />
        <Select value={roleFilter} onValueChange={(v) => setRoleFilter(v as UserRole | 'all')}>
          <SelectTrigger className="w-[12rem]"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">บทบาททั้งหมด</SelectItem>
            {ROLE_ORDER.map((r) => (
              <SelectItem key={r} value={r}>{ROLE_LABEL[r]}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>อีเมล</TableHead>
            <TableHead>ชื่อที่แสดง</TableHead>
            <TableHead>บทบาท</TableHead>
            <TableHead>สถานะ</TableHead>
            <TableHead>สร้างเมื่อ</TableHead>
            <TableHead className="text-right">การจัดการ</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading && (
            <TableRow><TableCell colSpan={6}>กำลังโหลด...</TableCell></TableRow>
          )}
          {isError && !isLoading && (
            <TableRow><TableCell colSpan={6}>เกิดข้อผิดพลาดในการโหลดข้อมูล</TableCell></TableRow>
          )}
          {!isLoading && !isError && users.length === 0 && (
            <TableRow><TableCell colSpan={6}>ไม่พบผู้ใช้</TableCell></TableRow>
          )}
          {users.map((u) => (
            <TableRow key={u.id}>
              <TableCell>{u.email}</TableCell>
              <TableCell>{u.displayName}</TableCell>
              <TableCell>
                <Badge variant={u.role === 'admin' ? 'default' : 'secondary'}>
                  {ROLE_LABEL[u.role] ?? u.role}
                </Badge>
              </TableCell>
              <TableCell>
                <Badge variant={u.isActive ? 'default' : 'outline'}>
                  {u.isActive ? 'ใช้งาน' : 'ปิดใช้งาน'}
                </Badge>
              </TableCell>
              <TableCell>{new Date(u.createdAt).toLocaleDateString('th-TH')}</TableCell>
              <TableCell className="text-right space-x-2">
                <Button variant="ghost" size="sm" onClick={() => openEdit(u)}>แก้ไข</Button>
                <Button variant="ghost" size="sm" onClick={() => setToggling(u)}>
                  {u.isActive ? 'ปิดใช้งาน' : 'เปิดใช้งาน'}
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <UserFormDialog open={formOpen} onOpenChange={setFormOpen} user={editing} />
      <DeactivateUserDialog user={toggling} onOpenChange={(open) => { if (!open) setToggling(null); }} />
    </div>
  );
}
