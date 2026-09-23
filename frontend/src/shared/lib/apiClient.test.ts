import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/shared/lib/oidc', () => ({
  ensureToken: vi.fn().mockResolvedValue('tok123'),
  isAuthenticated: vi.fn().mockReturnValue(true),
  login: vi.fn(),
}));

import { ensureToken } from '@/shared/lib/oidc';
import { axiosInstance } from '@/shared/lib/apiClient';

describe('apiClient request interceptor', () => {
  beforeEach(() => {
    vi.mocked(ensureToken).mockResolvedValue('tok123');
  });

  it('attaches the bearer token when one exists', async () => {
    const cfg = await (axiosInstance.interceptors.request as any).handlers[0].fulfilled({
      headers: {},
    });
    expect(cfg.headers.Authorization).toBe('Bearer tok123');
  });

  it('omits the Authorization header when no token exists', async () => {
    vi.mocked(ensureToken).mockResolvedValue(undefined);
    const cfg = await (axiosInstance.interceptors.request as any).handlers[0].fulfilled({
      headers: {},
    });
    expect(cfg.headers.Authorization).toBeUndefined();
  });
});
