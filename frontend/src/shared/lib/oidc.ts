import { UserManager, WebStorageStateStore, type User } from 'oidc-client-ts';

const appConfig = (window as any).__APP_CONFIG__;

const authority = appConfig?.OIDC_AUTHORITY || window.location.origin;
const clientId = appConfig?.OIDC_CLIENT_ID || 'chatbotportal-web';

export const userManager = new UserManager({
  authority,
  client_id: clientId,
  redirect_uri: `${window.location.origin}/auth/callback`,
  post_logout_redirect_uri: window.location.origin,
  response_type: 'code',
  scope: 'openid profile email offline_access',
  automaticSilentRenew: true,
  userStore: new WebStorageStateStore({ store: window.localStorage }),
});

let currentUser: User | null = null;

/** Load any persisted session on app start. Returns true when a valid one exists. */
export async function initAuth(): Promise<boolean> {
  currentUser = await userManager.getUser();
  return !!currentUser && !currentUser.expired;
}

/** Complete the Authorization Code + PKCE flow on the /auth/callback route. */
export async function completeLogin(): Promise<User> {
  currentUser = await userManager.signinRedirectCallback();
  return currentUser;
}

export function isAuthenticated(): boolean {
  return !!currentUser && !currentUser.expired;
}

export function getToken(): string | undefined {
  return currentUser?.access_token;
}

/** Return a valid access token, silently renewing it first when possible. */
export async function ensureToken(): Promise<string | undefined> {
  if (currentUser && !currentUser.expired) {
    return currentUser.access_token;
  }
  try {
    currentUser = await userManager.signinSilent();
    return currentUser?.access_token;
  } catch {
    return undefined;
  }
}

/** Redirect to the provider's login page; returns to `returnTo` afterwards. */
export function login(returnTo: string = window.location.pathname + window.location.search): Promise<void> {
  return userManager.signinRedirect({ state: { returnTo } });
}

export async function logout(): Promise<void> {
  currentUser = null;
  await userManager.signoutRedirect();
}
