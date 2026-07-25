import { lazy, Suspense } from "react";
import { Toaster } from "@/shared/components/ui/toaster";
import { Toaster as Sonner } from "@/shared/components/ui/sonner";
import { TooltipProvider } from "@/shared/components/ui/tooltip";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { ThemeProvider } from "@/shared/components/ThemeProvider";
import { AuthProvider } from "@/features/auth/useAuth";
import { ProtectedRoute } from "@/features/auth/ProtectedRoute";
import { AppLayout } from "@/shared/components/layout/AppLayout";
import { TextScaleProvider } from "@/shared/hooks/useTextScale";
import { SettingsIndexRedirect } from "@/features/settings/SettingsLayout";

// Lazy-loaded page routes — each becomes its own chunk
const ChatPage = lazy(() => import("@/features/chat/ChatPage"));
const DashboardPage = lazy(() => import("@/features/dashboard/DashboardPage"));
const ExecutivePage = lazy(() => import("@/features/executive/ExecutivePage"));
const HealthPage = lazy(() => import("@/features/health/HealthPage"));
const HeatmapPage = lazy(() => import("@/features/heatmap/HeatmapPage"));
const AgenciesPage = lazy(() => import("@/features/agencies/AgenciesPage"));
const AgencyDetailPage = lazy(() => import("@/features/agencies/detail/AgencyDetailPage"));
const AgencyWizardPage = lazy(() => import("@/features/agencies/wizard/AgencyWizardPage"));
const HistoryPage = lazy(() => import("@/features/history/HistoryPage"));
const ArchitecturePage = lazy(() => import("@/features/architecture/ArchitecturePage"));
const ConnectionLogsPage = lazy(() => import("@/features/connection-logs/ConnectionLogsPage"));
const PublicPortal = lazy(() => import("@/features/public/PublicPortal"));
const InfoPage = lazy(() => import("@/features/public/InfoPage"));
const StatusPage = lazy(() => import("@/features/status/StatusPage"));
const LoginPage = lazy(() => import("@/features/auth/LoginPage"));
const ApiKeysPage = lazy(() => import("@/features/api-keys/ApiKeysPage"));
const SettingsPage = lazy(() => import("@/features/settings/SettingsPage"));
const SettingsLayout = lazy(() => import("@/features/settings/SettingsLayout"));
const LlmSettingsPage = lazy(() => import("@/features/llm/LlmSettingsPage"));
const PopularQuestionsPage = lazy(() => import("@/features/popular-questions/PopularQuestionsPage"));
const UsersPage = lazy(() => import("@/features/users/UsersPage"));
const AuditLogPage = lazy(() => import("@/features/audit/AuditLogPage"));
const UsageAnalyticsPage = lazy(() => import("@/features/usage/UsageAnalyticsPage"));
const FeedbackPage = lazy(() => import("@/features/feedback/FeedbackPage"));
const NotFound = lazy(() => import("@/shared/NotFound"));

function RouteFallback() {
  return (
    <div className="p-6 space-y-4">
      <Skeleton className="h-12 w-96" />
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-32" />
        ))}
      </div>
      <Skeleton className="h-80" />
    </div>
  );
}

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem disableTransitionOnChange>
      <AuthProvider>
        <TooltipProvider>
          <Toaster />
          <Sonner />
          <BrowserRouter>
            <TextScaleProvider>
            <Suspense fallback={<RouteFallback />}>
            <Routes>
              <Route path="/" element={<PublicPortal />} />
              <Route path="/about" element={<InfoPage />} />
              <Route path="/data-policy" element={<InfoPage />} />
              <Route path="/contact" element={<InfoPage />} />
              <Route path="/status" element={<StatusPage />} />
              <Route path="/login" element={<LoginPage />} />

              <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
                {/* Every authenticated role */}
                <Route path="/chat" element={<ChatPage />} />
                <Route path="/architecture" element={<ArchitecturePage />} />
                {/* Own conversation history — the API scopes non-admins to their own rows. */}
                <Route path="/history" element={<HistoryPage />} />

                {/* staff + admin: read-only ops dashboards */}
                <Route element={<ProtectedRoute allowedRoles={["staff", "admin"]}><Outlet /></ProtectedRoute>}>
                  <Route path="/dashboard" element={<DashboardPage />} />
                  <Route path="/executive" element={<ExecutivePage />} />
                  <Route path="/health" element={<HealthPage />} />
                  <Route path="/heatmap" element={<HeatmapPage />} />
                  <Route path="/feedback" element={<FeedbackPage />} />
                </Route>

                {/* admin only */}
                <Route element={<ProtectedRoute allowedRoles={["admin"]}><Outlet /></ProtectedRoute>}>
                  <Route path="/agencies" element={<AgenciesPage />} />
                  <Route path="/agencies/:id" element={<AgencyDetailPage />} />
                  <Route path="/agencies/new" element={<AgencyWizardPage />} />
                  <Route path="/agencies/:id/setup" element={<AgencyWizardPage />} />
                </Route>

                {/* Merged Settings area — nested tabs. /settings is authenticated-only
                    because it contains the all-roles Usage tab; admin tabs are guarded
                    individually so deep links are blocked, not just hidden. */}
                <Route path="/settings" element={<SettingsLayout />}>
                  <Route index element={<SettingsIndexRedirect />} />
                  <Route path="system" element={<ProtectedRoute requireAdmin><SettingsPage /></ProtectedRoute>} />
                  <Route path="llm" element={<ProtectedRoute requireAdmin><LlmSettingsPage /></ProtectedRoute>} />
                  <Route path="api-keys" element={<ProtectedRoute requireAdmin><ApiKeysPage /></ProtectedRoute>} />
                  <Route path="users" element={<ProtectedRoute requireAdmin><UsersPage /></ProtectedRoute>} />
                  <Route path="usage" element={<ProtectedRoute allowedRoles={["staff", "admin"]}><UsageAnalyticsPage /></ProtectedRoute>} />
                  <Route path="connections" element={<ProtectedRoute requireAdmin><ConnectionLogsPage /></ProtectedRoute>} />
                  <Route path="audit" element={<ProtectedRoute requireAdmin><AuditLogPage /></ProtectedRoute>} />
                </Route>

                {/* Redirect old top-level routes to their new tab */}
                <Route path="/api-keys" element={<Navigate to="/settings/api-keys" replace />} />
                <Route path="/users" element={<Navigate to="/settings/users" replace />} />
                <Route path="/usage" element={<Navigate to="/settings/usage" replace />} />
                <Route path="/connection-logs" element={<Navigate to="/settings/connections" replace />} />
                <Route path="/audit-log" element={<Navigate to="/settings/audit" replace />} />
                <Route path="/llm-settings" element={<Navigate to="/settings/llm" replace />} />
                <Route path="/llm-providers" element={<Navigate to="/settings/llm" replace />} />
                <Route path="/llm-routes" element={<Navigate to="/settings/llm" replace />} />

                <Route path="/popular-questions" element={<ProtectedRoute requireAdmin><PopularQuestionsPage /></ProtectedRoute>} />
              </Route>

              <Route path="*" element={<NotFound />} />
            </Routes>
            </Suspense>
            </TextScaleProvider>
          </BrowserRouter>
        </TooltipProvider>
      </AuthProvider>
    </ThemeProvider>
  </QueryClientProvider>
);

export default App;
