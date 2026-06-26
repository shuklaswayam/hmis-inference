import { PagePlaceholder } from '@/components/layout/PageHeader'
import { Siren } from 'lucide-react'

export function NotFoundPage() {
  return (
    <PagePlaceholder
      title="Not Found"
      description="The page you're looking for has been moved or never existed."
      phase="404"
      icon={Siren}
    />
  )
}
