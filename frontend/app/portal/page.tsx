// Portal root — redirect to dashboard (T074 entry point).
import { redirect } from 'next/navigation'

export default function PortalRoot() {
  redirect('/portal/dashboard')
}
