import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Loader2 } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { ScrollArea } from '@/components/ui/scroll-area'
import { AlertFeed } from '@/components/AlertFeed'
import { AlertDetail } from '@/components/AlertDetail'
import { DistrictFilter } from '@/components/DistrictFilter'
import client from '@/api/client'
import { useState, useEffect } from 'react'

import type { Alert } from '@/types/alerts'

export default function AlertsPage() {
  const [districtId, setDistrictId] = useState<string | null>(null)
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null)
  const [filter, setFilter] = useState<'ALL' | string>('ALL')

  const alertsQuery = useQuery<Alert[]>({
    queryKey: ['alerts', 'page', districtId],
    queryFn: async ({ signal }) => {
      const params: Record<string, string | number> = {}
      if (districtId) params.district_id = districtId
      const res = await client.get('/api/v1/alerts/', { params, signal })
      return (res.data ?? []) as Alert[]
    },
  })

  useEffect(() => {
    if (!selectedAlert && alertsQuery.data && alertsQuery.data.length > 0) {
      setSelectedAlert(alertsQuery.data[0])
    }
  }, [alertsQuery.data, selectedAlert])

  // Belt-and-braces: clear the right-panel selection whenever the filter /
  // district changes. The autoselect effect above then picks the first
  // alert of the new list, so the user never sits on a stale investigation.
  // The `isFilteredOut` flag on AlertDetail is a backstop for any race
  // window during fetch where the previously-selected alert is shown between
  // the request going out and the autoselect firing.
  useEffect(() => {
    setSelectedAlert(null)
  }, [districtId])

  const isSelectedFilteredOut =
    !!selectedAlert
    && !!alertsQuery.data
    && !alertsQuery.data.some((a) => a.id === selectedAlert!.id)

  return (
    <section className="animate-fade-in">
      <PageHeader
        eyebrow="Workspace"
        title="Alerts"
        description="Every active signal, sorted by severity. Click any alert to open its investigation."
        actions={
          <>
            <Badge variant="critical">{alertsQuery.data?.length ?? '—'} active</Badge>
            <DistrictFilter value={districtId} onChange={(v) => setDistrictId(v as string | null)} />
          </>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(320px,32%)_1fr] min-h-[560px]">
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border/60">
            <span className="text-body-sm font-medium">Inbox</span>
            {alertsQuery.isFetching && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
         </div>
          <ScrollArea className="h-[560px]">
            {alertsQuery.isLoading ? (
              <div className="p-3 space-y-2">
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-16 rounded-md" />
                ))}
             </div>
            ) : alertsQuery.isError ? (
              <div className="p-10 text-center">
                <AlertTriangle className="h-5 w-5 text-severity-critical mx-auto mb-2" />
                <p className="text-body-sm text-muted-foreground">Failed to load alerts</p>
                <Button variant="outline" size="sm" className="mt-3" onClick={() => alertsQuery.refetch()}>
                  Retry
               </Button>
             </div>
            ) : (
              <AlertFeed
                alerts={alertsQuery.data ?? []}
                filter={filter}
                onFilterChange={setFilter}
                selectedAlert={selectedAlert}
                onSelectAlert={setSelectedAlert}
              />
            )}
         </ScrollArea>
       </Card>

        <Card className="overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border/60">
            <span className="text-body-sm font-medium">Investigation</span>
            <span className="text-caption text-muted-foreground">
              {selectedAlert ? `Alert #${selectedAlert.id}` : 'No selection'}
           </span>
         </div>
          <ScrollArea className="h-[560px]">
            <AlertDetail
              alert={selectedAlert}
              isFilteredOut={isSelectedFilteredOut}
              onClearFilter={() => setDistrictId(null)}
            />
         </ScrollArea>
       </Card>
     </div>
   </section>
  )
}
