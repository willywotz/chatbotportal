import { createRoot } from "react-dom/client";

import App from "./App.tsx";
import { initAuth } from "@/shared/lib/oidc";
import "./index.css";

async function enableMocking(): Promise<void> {
  const { worker } = await import("./mocks/browser");
  await worker.start({ onUnhandledRequest: "bypass" });
}

async function bootstrap(): Promise<void> {
  // Mock mode has no real OIDC provider to talk to; MSW stands in for it.
  if (import.meta.env.VITE_USE_MOCKS === "true") {
    await enableMocking();
  } else {
    await initAuth();
  }
  createRoot(document.getElementById("root")!).render(<App />);
}

bootstrap();
