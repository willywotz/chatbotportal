import { WebStorageStateStore } from 'oidc-client-ts';
import type { AuthProviderProps } from 'react-oidc-context';

const appConfig = (window as { __APP_CONFIG__?: Record<string, string> }).__APP_CONFIG__;

const authority = appConfig?.OIDC_AUTHORITY || window.location.origin;
const clientId = appConfig?.OIDC_CLIENT_ID || 'chatbotportal-web';

/**
 * OIDC provider config for react-oidc-context. Authorization Code + PKCE (S256),
 * refresh-token silent renew. Values come from the runtime `/config.js`
 * (window.__APP_CONFIG__), falling back to the current origin.
 */
export const oidcConfig: AuthProviderProps = {
  authority,
  client_id: clientId,
  redirect_uri: `${window.location.origin}/auth/callback`,
  post_logout_redirect_uri: window.location.origin,
  response_type: 'code',
  scope: 'openid profile email offline_access',
  automaticSilentRenew: true,
  userStore: new WebStorageStateStore({ store: window.localStorage }),
  // Strip ?code&state from the URL once the callback is processed so a refresh
  // of /auth/callback does not replay the (now consumed) authorization code.
  onSigninCallback: () => {
    window.history.replaceState({}, document.title, window.location.pathname);
  },
};
