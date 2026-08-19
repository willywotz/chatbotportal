import Keycloak from 'keycloak-js';

const env = import.meta.env;
export const keycloak = new Keycloak({
  url: (env.VITE_KEYCLOAK_URL as string) || 'http://localhost:8080/auth',
  realm: (env.VITE_KEYCLOAK_REALM as string) || 'chatbotportal',
  clientId: (env.VITE_KEYCLOAK_CLIENT_ID as string) || 'portal-spa',
});

let initPromise: Promise<boolean> | null = null;

export function initKeycloak(): Promise<boolean> {
  // check-sso: does NOT force login, so guests and public pages work; login is
  // triggered on demand by ProtectedRoute / the login button.
  if (!initPromise) {
    initPromise = keycloak.init({
      onLoad: 'check-sso',
      pkceMethod: 'S256',
      silentCheckSsoRedirectUri: `${window.location.origin}/silent-check-sso.html`,
      checkLoginIframe: false,
    });
  }
  return initPromise;
}

export const getToken = () => keycloak.token;
export const login = (redirectUri = window.location.href) => keycloak.login({ redirectUri });
export const logout = (redirectUri = window.location.origin) => keycloak.logout({ redirectUri });
export const updateToken = (minValidity = 30) => keycloak.updateToken(minValidity);
