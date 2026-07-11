import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { AppShell } from '@/layouts/AppShell'
import HealthCommissionerDashboard from '@/pages/HealthCommissionerDashboard'
import AuditLogPage from '@/pages/AuditLogPage'
import DrilldownPage from '@/pages/DrilldownPage'
import LoginPage from '@/pages/LoginPage'
import FacilitiesPage from '@/pages/FacilitiesPage'
import AnalyticsPage from '@/pages/AnalyticsPage'
import SettingsPage from '@/pages/SettingsPage'
import { NotFoundPage } from '@/pages/placeholders'
import { AuthProvider, useAuth } from '@/auth/AuthContext'
import { I18nProvider } from '@/i18n'

function ProtectedShell() {
  const { isAuthenticated } = useAuth()
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  return <AppShell />
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <I18nProvider>
        <AuthProvider>
          <Routes>
            <Route path="login" element={<LoginPage />} />
            <Route element={<ProtectedShell />}>
              <Route index element={<HealthCommissionerDashboard />} />
              <Route path="audit" element={<AuditLogPage />} />
              <Route path="drilldown/:kind" element={<DrilldownPage />} />
              <Route path="drilldown/:kind/:id" element={<DrilldownPage />} />
              <Route path="drilldown/:kind/:id/:disease" element={<DrilldownPage />} />
              <Route path="facilities" element={<FacilitiesPage />} />
              <Route path="analytics" element={<AnalyticsPage />} />
              <Route path="alerts" element={<Navigate to="/" replace />} />
              <Route path="ai" element={<Navigate to="/" replace />} />
              <Route path="investigations" element={<Navigate to="/" replace />} />
              <Route path="reports" element={<Navigate to="/" replace />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="gantt" element={<Navigate to="/" replace />} />
              <Route path="*" element={<NotFoundPage />} />
           </Route>
         </Routes>
       </AuthProvider>
     </I18nProvider>
   </BrowserRouter>
  )
}
