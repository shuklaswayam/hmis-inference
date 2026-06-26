import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { AppShell } from '@/layouts/AppShell'
import OverviewPage from '@/pages/OverviewPage'
import AlertsPage from '@/pages/AlertsPage'
import InvestigationsPage from '@/pages/InvestigationsPage'
import FacilitiesPage from '@/pages/FacilitiesPage'
import AnalyticsPage from '@/pages/AnalyticsPage'
import AIPage from '@/pages/AIPage'
import ReportsPage from '@/pages/ReportsPage'
import SettingsPage from '@/pages/SettingsPage'
import { NotFoundPage } from '@/pages/placeholders'

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<OverviewPage />} />
          <Route path="alerts" element={<AlertsPage />} />
          <Route path="investigations" element={<InvestigationsPage />} />
          <Route path="facilities" element={<FacilitiesPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="ai" element={<AIPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="gantt" element={<Navigate to="/reports" replace />} />
          <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  </BrowserRouter>
  )
}
