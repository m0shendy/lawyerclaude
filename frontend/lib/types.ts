// Single source for frontend payload types (mirrors backend/app/models/entities.py).

export type Role = 'partner_manager' | 'lawyer' | 'paralegal' | 'secretary'
export type UserStatus = 'active' | 'inactive'
export type DocumentStatus = 'pending' | 'processing' | 'ready' | 'low_confidence' | 'failed'
export type AiOutputType = 'summary' | 'extraction' | 'analysis' | 'clause_flag' | 'risk_signal'
export type ReviewState = 'draft_unreviewed' | 'approved'
export type DeadlineType = 'general' | 'appeal_istinaf' | 'mu_arada' | 'naqd'
export type TaskStatus = 'open' | 'in_progress' | 'done' | 'cancelled'

export const ROLE_LABELS: Record<Role, string> = {
  partner_manager: 'شريك / مدير',
  lawyer: 'محامٍ',
  paralegal: 'مساعد قانوني',
  secretary: 'سكرتير',
}

export const DOCUMENT_STATUS_LABELS: Record<DocumentStatus, string> = {
  pending: 'في الانتظار',
  processing: 'قيد المعالجة',
  ready: 'جاهز',
  low_confidence: 'جودة مسح منخفضة',
  failed: 'فشل',
}

export const DEADLINE_TYPE_LABELS: Record<DeadlineType, string> = {
  general: 'موعد عام',
  appeal_istinaf: 'ميعاد استئناف',
  mu_arada: 'ميعاد معارضة',
  naqd: 'ميعاد نقض',
}

export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  open: 'مفتوحة',
  in_progress: 'قيد التنفيذ',
  done: 'منجزة',
  cancelled: 'ملغاة',
}

export interface User {
  id: string
  full_name: string
  email: string
  phone: string | null
  role: Role
  status: UserStatus
  created_at: string
}

export interface Case {
  id: string
  title: string
  client_name: string
  case_number: string | null
  court: string | null
  case_type: string | null
  status: string
  created_by: string | null
  created_at: string
}

export interface CaseAssignment {
  id: string
  case_id: string
  user_id: string
  created_at: string
}

export interface Document {
  id: string
  case_id: string
  file_path: string
  file_name: string
  source_type: 'text_pdf' | 'scanned'
  status: DocumentStatus
  ocr_confidence: number | null
  error_detail: string | null
  uploaded_by: string | null
  uploaded_at: string
}

export interface SourceLink {
  chunk_id: string
  document_id: string
  page_ref: number | null
}

export interface AiOutput {
  id: string
  document_id: string | null
  case_id: string | null
  type: AiOutputType
  content: Record<string, unknown>
  source_links: SourceLink[]
  review_state: ReviewState
  low_confidence_flag: boolean
  generated_by_model: string | null
  created_at: string
  approved_by: string | null
  approved_at: string | null
  approved_version: number | null
}

export interface Deadline {
  id: string
  case_id: string
  type: DeadlineType
  title: string
  basis: string | null
  due_date: string
  suggested_date: string | null
  confirmed: boolean
  confirmed_by: string | null
  confirmed_at: string | null
  responsible_user_id: string
  derived_from_document_id: string | null
  low_confidence_flag: boolean
  acknowledged_at: string | null
  created_at: string
}

export interface TaskItem {
  id: string
  case_id: string
  assigned_to: string
  description: string
  due_date: string | null
  status: TaskStatus
  created_at: string
}

export interface AuditEntry {
  id: number
  who_user_id: string | null
  who_role: string | null
  when_ts: string
  entity_table: string
  record_id: string | null
  action: 'create' | 'update' | 'delete'
  change_detail: Record<string, { old: unknown; new: unknown }> | null
  context: string | null
}

export interface FirmSettings {
  id: string
  firm_name: string
  locale: string
  waha_url: string | null
  waha_key_set: boolean
  llm_api_key_set: boolean
  embedding_config: { model: string; dimension: number }
  reminder_lead_points: string[]
  feature_appeal_deadlines: boolean
  subscription_metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface Me {
  id: string
  full_name: string
  email: string
  phone: string | null
  role: Role
  assigned_cases: Case[]
}

// ── reports (GET /reports/daily) ──────────────────────────────────────────────

export interface ReportItem {
  kind: string
  title: string
  audit_id?: number
  ref_table?: string
  ref_id?: string
  case_title?: string
  when?: string
}

export interface ReportSection {
  heading: string
  prose: string
  items: ReportItem[]
}

export interface DailyReport {
  report_date: string
  what_happened: ReportSection
  tomorrow: ReportSection
}

// ── assistant (POST /assistant/query) ─────────────────────────────────────────

export interface AssistantAnswer {
  answer: string
  sources: SourceLink[]
  grounded: boolean
  saved_output_id: string | null
}
