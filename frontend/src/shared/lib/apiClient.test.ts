import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/shared/lib/keycloak', () => ({
  keycloak: { authenticated: true, token: 'tok123' },
  updateToken: vi.fn().mockResolvedValue(false),
}));

import { keycloak } from '@/shared/lib/keycloak';
import { axiosInstance } from '@/shared/lib/apiClient';

describe('apiClient request interceptor', () => {
  beforeEach(() => {
    keycloak.token = 'tok123';
  });

  it('attaches the bearer token when one exists', async () => {
    const cfg = await (axiosInstance.interceptors.request as any).handlers[0].fulfilled({
      headers: {},
    });
    expect(cfg.headers.Authorization).toBe('Bearer tok123');
  });

  it('omits the Authorization header when no token exists', async () => {
    keycloak.token = undefined;
    const cfg = await (axiosInstance.interceptors.request as any).handlers[0].fulfilled({
      headers: {},
    });
    expect(cfg.headers.Authorization).toBeUndefined();
  });
});
