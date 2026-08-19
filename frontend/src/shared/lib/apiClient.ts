/**
 * Axios-based HTTP client for the FastAPI backend.
 *
 * Base URL:  VITE_API_BASE_URL  (default: http://localhost:8000)
 *
 * A request interceptor refreshes the Keycloak token (when authenticated)
 * and attaches it as `Authorization: Bearer <token>`; no session cookie is
 * sent.
 *
 * A response interceptor unwraps Axios errors and surfaces the FastAPI
 * `detail` field as a plain Error message, and re-triggers Keycloak login
 * on a 401 for a previously-authenticated session.
 *
 * Usage:
 *   import { api } from '@/shared/lib/apiClient';
 *   const data = await api.get<AgencyList>('/api/v1/agencies');
 *   const result = await api.post('/api/v1/chat', { query: '...' });
 */

import axios, { type AxiosInstance, type AxiosResponse } from 'axios';

import { keycloak, updateToken } from '@/shared/lib/keycloak';

var baseURL = import.meta.env.VITE_API_BASE_URL as string | undefined;

if (!baseURL || baseURL.trim() === '') {
  baseURL = window.location.origin;
}

const axiosInstance: AxiosInstance = axios.create({
  baseURL: baseURL,
  headers: { 'Content-Type': 'application/json' },
});

// -- Request interceptor: refresh and attach the Keycloak bearer token ------
axiosInstance.interceptors.request.use(async (config) => {
  if (keycloak.authenticated) {
    try {
      await updateToken(30);
    } catch {
      // Refresh failed; let the request proceed and fail with a 401.
    }
  }
  if (keycloak.token) {
    // config.headers is always defined here (axios sets it before running
    // interceptors); a direct property assignment works whether it's a
    // plain object (as in apiClient.test.ts) or a real AxiosHeaders instance.
    (config.headers as Record<string, string>).Authorization = `Bearer ${keycloak.token}`;
  }
  return config;
});

// -- Response interceptor: surface FastAPI error message as Error ------------
axiosInstance.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error) => {
    // Only re-login when a previously-authenticated session got a 401;
    // an anonymous 401 must not trigger a redirect loop.
    if (error?.response?.status === 401 && keycloak.authenticated) {
      keycloak.login();
    }
    const data = error?.response?.data;
    // New envelope shape: {"error": {"code", "message", "retryable"}}
    const envelopeMessage = data?.error?.message;
    // Legacy shape fallback: {"detail": "..."} or [{"msg": "..."}] (422 validation)
    const detail = data?.detail;
    const message =
      typeof envelopeMessage === 'string'
        ? envelopeMessage
        : typeof detail === 'string'
          ? detail
          : Array.isArray(detail)
            ? detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join(', ')
            : error.message ?? 'Request failed';
    return Promise.reject(new Error(message));
  }
);

async function req<T>(fn: () => Promise<AxiosResponse<T>>): Promise<T> {
  const res = await fn();
  return res.data;
}

export const api = {
  // `params` is `object`, not `Record<string, unknown>`: an interface has no
  // implicit index signature, so callers passing a typed params interface
  // (AuditLogParams, UsageParams, …) would not type-check against Record.
  get: <T = unknown>(path: string, params?: object) =>
    req<T>(() => axiosInstance.get<T>(path, { params })),

  post: <T = unknown>(path: string, body?: unknown) =>
    req<T>(() => axiosInstance.post<T>(path, body)),

  put: <T = unknown>(path: string, body?: unknown) =>
    req<T>(() => axiosInstance.put<T>(path, body)),

  patch: <T = unknown>(path: string, body?: unknown) =>
    req<T>(() => axiosInstance.patch<T>(path, body)),

  delete: <T = unknown>(path: string) =>
    req<T>(() => axiosInstance.delete<T>(path)),
};

/** Raw axios instance — use when you need full AxiosResponse access. */
export { axiosInstance };
