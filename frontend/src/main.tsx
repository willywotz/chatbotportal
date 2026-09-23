import { createRoot } from "react-dom/client";
import { AuthProvider } from "react-oidc-context";

import App from "./App.tsx";
import { oidcConfig } from "@/shared/lib/oidc";
import "./index.css";

async function enableMocking(): Promise<void> {
  const { worker } = await import("./mocks/browser");
  await worker.start({ onUnhandledRequest: "bypass" });
}

async function bootstrap(): Promise<void> {
  // Mock mode has no real OIDC provider to talk to; MSW stands in for it and the
  // auth hook returns a fixed admin (see useAuth).
  if (import.meta.env.VITE_USE_MOCKS === "true") {
    await enableMocking();
  }
  createRoot(document.getElementById("root")!).render(
    <AuthProvider {...oidcConfig}>
      <App />
    </AuthProvider>,
  );
}

bootstrap();
