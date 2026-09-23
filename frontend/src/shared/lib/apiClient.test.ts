import { describe, it, expect, beforeEach } from 'vitest';

import { setAccessToken } from '@/shared/lib/authToken';
import { axiosInstance } from '@/shared/lib/apiClient';

describe('apiClient request interceptor', () => {
  beforeEach(() => {
    setAccessToken('tok123');
  });

  it('attaches the bearer token when one exists', async () => {
    const cfg = await (axiosInstance.interceptors.request as any).handlers[0].fulfilled({
      headers: {},
    });
    expect(cfg.headers.Authorization).toBe('Bearer tok123');
  });

  it('omits the Authorization header when no token exists', async () => {
    setAccessToken(undefined);
    const cfg = await (axiosInstance.interceptors.request as any).handlers[0].fulfilled({
      headers: {},
    });
    expect(cfg.headers.Authorization).toBeUndefined();
  });
});
