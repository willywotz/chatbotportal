import { createRoot } from "react-dom/client";
import { AuthProvider } from "react-oidc-context";

import App from "./App.tsx";
import { oidcConfig } from "@/shared/lib/oidc";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <AuthProvider {...oidcConfig}>
    <App />
  </AuthProvider>,
);
