import { api } from '@/shared/lib/apiClient';
import type { Role } from '@/features/auth/roles';

export type UserRole = Role;

export interface ManagedUser {
  id: string;
  email: string;
  displayName: string;
  role: UserRole;
  avatarUrl: string | null;
  isActive: boolean;
  createdAt: string;
}

export interface UserListParams {
  search?: string;
  role?: UserRole;
  status?: 'active' | 'inactive' | 'all';
}

export interface CreateUserPayload {
  email: string;
  role: UserRole;
  display_name?: string | null;
  password: string;
}

export interface UpdateUserPayload {
  display_name?: string | null;
  role?: UserRole;
  password?: string;
}

export async function listUsers(params: UserListParams): Promise<ManagedUser[]> {
  const res = await api.get<{ data: ManagedUser[]; total: number }>('/api/v1/users', params);
  return res.data;
}

export async function createUser(payload: CreateUserPayload): Promise<{ user: ManagedUser }> {
  return api.post<{ user: ManagedUser }>('/api/v1/users', payload);
}

export async function updateUser(id: string, payload: UpdateUserPayload): Promise<ManagedUser> {
  return api.patch<ManagedUser>(`/api/v1/users/${id}`, payload);
}

export async function deactivateUser(id: string): Promise<ManagedUser> {
  return api.post<ManagedUser>(`/api/v1/users/${id}/deactivate`);
}

export async function activateUser(id: string): Promise<ManagedUser> {
  return api.post<ManagedUser>(`/api/v1/users/${id}/activate`);
}

export async function deleteUser(id: string): Promise<void> {
  await api.delete(`/api/v1/users/${id}`);
}
