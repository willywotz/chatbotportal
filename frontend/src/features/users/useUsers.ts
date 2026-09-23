import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  listUsers,
  createUser,
  updateUser,
  deactivateUser,
  activateUser,
  deleteUser,
  type UserListParams,
  type CreateUserPayload,
  type UpdateUserPayload,
} from './userApi';
import { STALE_TIME } from '@/shared/constants/query';

const KEY = 'users';

export function useUsers(params: UserListParams) {
  return useQuery({
    queryKey: [KEY, params],
    queryFn: () => listUsers(params),
    staleTime: STALE_TIME.normal,
  });
}

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateUserPayload) => createUser(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  });
}

export function useUpdateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: UpdateUserPayload }) => updateUser(id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  });
}

export function useSetUserActive() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      active ? activateUser(id) : deactivateUser(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  });
}

export function useDeleteUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteUser(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  });
}
