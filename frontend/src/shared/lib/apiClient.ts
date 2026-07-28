/**
 * Axios-based HTTP client for the FastAPI backend.
 *
 * Base URL:  VITE_API_BASE_URL  (default: http://localhost:8000)
 *
 * The instance sends the HttpOnly session cookie on every request
 * (`withCredentials: true`); no Authorization header is attached.
 *
 * A response interceptor unwraps Axios errors and surfaces the FastAPI
 * `detail` field as a plain Error message.
 *
 * Usage:
 *   import { api } from '@/shared/lib/apiClient';
 *   const data = await api.get<AgencyList>('/api/v1/agencies');
 *   const result = await api.post('/api/v1/chat', { query: '...' });
 */

import axios, { type AxiosInstance, type AxiosResponse } from 'axios';

// ---------------------------------------------------------------------------
// Axios instance
// ---------------------------------------------------------------------------

var baseURL = import.meta.env.VITE_API_BASE_URL as string | undefined;

if (!baseURL || baseURL.trim() === '') {
  baseURL = window.location.origin;
}

const axiosInstance: AxiosInstance = axios.create({
  baseURL: baseURL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
});

// -- Response interceptor: surface FastAPI error message as Error ------------
axiosInstance.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error) => {
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

// ---------------------------------------------------------------------------
// Typed helper — returns response.data directly (matches the old api.* surface)
// ---------------------------------------------------------------------------

async function req<T>(fn: () => Promise<AxiosResponse<T>>): Promise<T> {
  const res = await fn();
  return res.data;
}

// ---------------------------------------------------------------------------
// Public API  (drop-in replacement for the old fetch-based api object)
// ---------------------------------------------------------------------------

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
