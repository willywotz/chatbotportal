/**
 * Bridge between the React OIDC context and the non-React axios client.
 *
 * react-oidc-context owns the access token as React state; `apiClient` and the
 * SSE/fetch call sites are plain modules. `AuthTokenSync` (mounted inside the
 * provider) pushes the current token and a re-login callback here, and the
 * request/response interceptors read them.
 */
let accessToken: string | undefined;
let onUnauthenticated: (() => void) | undefined;

export function setAccessToken(token: string | undefined): void {
  accessToken = token;
}

export function getAccessToken(): string | undefined {
  return accessToken;
}

export function setOnUnauthenticated(cb: (() => void) | undefined): void {
  onUnauthenticated = cb;
}

export function notifyUnauthenticated(): void {
  onUnauthenticated?.();
}
