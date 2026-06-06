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

// ── Module A: Contacts ────────────────────────────────────────────────────────

export type ContactType =
  | 'client' | 'opposing_party' | 'opposing_counsel'
  | 'court' | 'judge' | 'notary' | 'government' | 'expert' | 'other'

export type ContactCaseRole =
  | 'client' | 'opposing_party' | 'opposing_counsel'
  | 'witness' | 'expert' | 'court' | 'other'

export const CONTACT_TYPE_LABELS: Record<ContactType, string> = {
  client: 'موكّل',
  opposing_party: 'طرف خصم',
  opposing_counsel: 'محامي الخصم',
  court: 'محكمة',
  judge: 'قاضٍ',
  notary: 'محضر',
  government: 'جهة حكومية',
  expert: 'خبير',
  other: 'أخرى',
}

export const CONTACT_CASE_ROLE_LABELS: Record<ContactCaseRole, string> = {
  client: 'موكّل',
  opposing_party: 'طرف خصم',
  opposing_counsel: 'محامي الخصم',
  witness: 'شاهد',
  expert: 'خبير',
  court: 'محكمة',
  other: 'أخرى',
}

export interface Contact {
  id: string
  type: ContactType
  name_ar: string
  name_en: string | null
  national_id: string | null
  tax_id: string | null
  phone: string | null
  email: string | null
  address: string | null
  notes: string | null
  is_active: boolean
  created_by: string | null
  created_at: string
  updated_at: string
}

export interface ContactDetail extends Contact {
  cases: { case_id: string; title: string; case_number: string | null; role: ContactCaseRole }[]
}

export interface CaseContactLink {
  id: string
  case_id: string
  contact_id: string
  role: ContactCaseRole
  notes: string | null
  added_at: string
  name_ar?: string
  name_en?: string | null
  type?: ContactType
  phone?: string | null
}

// ── Module B: Billing ─────────────────────────────────────────────────────────

export type InvoiceStatus = 'draft' | 'sent' | 'partial' | 'paid' | 'cancelled' | 'overdue'
export type PaymentMethod = 'cash' | 'bank_transfer' | 'check' | 'other'

export const INVOICE_STATUS_LABELS: Record<InvoiceStatus, string> = {
  draft: 'مسودة',
  sent: 'مُرسَلة',
  partial: 'مدفوعة جزئياً',
  paid: 'مدفوعة',
  cancelled: 'ملغاة',
  overdue: 'متأخرة',
}

export const INVOICE_STATUS_COLORS: Record<InvoiceStatus, string> = {
  draft: 'bg-gray-100 text-gray-700',
  sent: 'bg-blue-100 text-blue-700',
  partial: 'bg-yellow-100 text-yellow-700',
  paid: 'bg-green-100 text-green-700',
  cancelled: 'bg-red-100 text-red-700',
  overdue: 'bg-red-200 text-red-800',
}

export const PAYMENT_METHOD_LABELS: Record<PaymentMethod, string> = {
  cash: 'نقد',
  bank_transfer: 'تحويل بنكي',
  check: 'شيك',
  other: 'أخرى',
}

export interface TimeEntry {
  id: string
  case_id: string
  user_id: string
  date: string
  duration_minutes: number
  description: string
  is_billable: boolean
  rate_egp: string | null
  amount_egp: string | null
  invoice_id: string | null
  created_at: string
  updated_at: string
}

export interface InvoiceLineItem {
  id: string
  invoice_id: string
  description: string
  quantity: string
  unit_price_egp: string
  total_egp: string
  sort_order: number
}

export interface Invoice {
  id: string
  invoice_number: string
  case_id: string | null
  contact_id: string | null
  issue_date: string
  due_date: string
  status: InvoiceStatus
  subtotal_egp: string
  tax_rate: string
  tax_egp: string
  discount_egp: string
  total_egp: string
  notes: string | null
  created_by: string | null
  created_at: string
  updated_at: string
}

export interface InvoiceDetail extends Invoice {
  line_items: InvoiceLineItem[]
  payments: Payment[]
  amount_paid: string
  amount_due: string
}

export interface Payment {
  id: string
  invoice_id: string
  amount_egp: string
  payment_date: string
  method: PaymentMethod | null
  reference: string | null
  notes: string | null
  recorded_by: string | null
  created_at: string
}

export interface BillingRate {
  id: string
  user_id: string
  rate_egp: string
  effective_from: string
  created_at: string
}

// ── Module C: Hearings ────────────────────────────────────────────────────────

export type HearingStatus = 'scheduled' | 'held' | 'adjourned' | 'cancelled'

export const HEARING_STATUS_LABELS: Record<HearingStatus, string> = {
  scheduled: 'مجدولة',
  held: 'منعقدة',
  adjourned: 'مؤجلة',
  cancelled: 'ملغاة',
}

export const HEARING_STATUS_COLORS: Record<HearingStatus, string> = {
  scheduled: 'bg-blue-100 text-blue-700',
  held: 'bg-green-100 text-green-700',
  adjourned: 'bg-yellow-100 text-yellow-700',
  cancelled: 'bg-red-100 text-red-700',
}

export interface Hearing {
  id: string
  case_id: string
  hearing_date: string
  court_name: string
  court_room: string | null
  judge_contact_id: string | null
  assigned_lawyer_id: string | null
  status: HearingStatus
  result: string | null
  next_hearing_date: string | null
  next_hearing_court: string | null
  notes: string | null
  reminder_sent_7d: boolean
  reminder_sent_3d: boolean
  reminder_sent_1d: boolean
  reminder_sent_0d: boolean
  created_by: string | null
  created_at: string
  updated_at: string
}

export interface HearingWithCase extends Hearing {
  case_title: string
  case_number: string | null
}

// ── Module D: Templates ───────────────────────────────────────────────────────

export type TemplateCategory =
  | 'contract' | 'pleading' | 'power_of_attorney'
  | 'letter' | 'memo' | 'notice' | 'court_submission' | 'other'

export const TEMPLATE_CATEGORY_LABELS: Record<TemplateCategory, string> = {
  contract: 'عقد',
  pleading: 'مذكرة',
  power_of_attorney: 'توكيل',
  letter: 'خطاب',
  memo: 'مذكرة داخلية',
  notice: 'إخطار',
  court_submission: 'تقديم للمحكمة',
  other: 'أخرى',
}

export interface MergeFieldDef {
  key: string
  label_ar: string
  type: 'text' | 'date' | 'number'
  required: boolean
}

export interface TemplateSummary {
  id: string
  is_platform: boolean
  name_ar: string
  category: TemplateCategory
  is_active: boolean
  version: number
  merge_fields: MergeFieldDef[]
  created_at: string
}

export interface Template extends TemplateSummary {
  content: string
  created_by: string | null
  updated_at: string
}

// ── Module E: Correspondence ──────────────────────────────────────────────────

export type CorrespondenceDirection = 'inbound' | 'outbound'
export type CorrespondenceChannel = 'email' | 'letter' | 'fax' | 'whatsapp' | 'phone' | 'court' | 'other'

export const CHANNEL_LABELS: Record<CorrespondenceChannel, string> = {
  email: 'بريد إلكتروني',
  letter: 'خطاب',
  fax: 'فاكس',
  whatsapp: 'واتساب',
  phone: 'هاتف',
  court: 'محكمة',
  other: 'أخرى',
}


export interface Correspondence {
  id: string
  case_id: string
  direction: CorrespondenceDirection
  channel: CorrespondenceChannel
  subject: string
  body_summary: string | null
  document_id: string | null
  contact_id: string | null
  sent_received_at: string
  recorded_by: string | null
  created_at: string
}

// ── Analytics (Modules F & H) ─────────────────────────────────────────────────

export interface RevenuePeriod {
  period: string
  billed_egp: string
  collected_egp: string
  outstanding_egp: string
}

export interface AgingBucket {
  bucket: string
  count: number
  total_egp: string
}

export interface LawyerProductivity {
  user_id: string
  name: string
  hours_logged: string
  billable_hours: string
  billed_egp: string
  collected_egp: string
  utilization_rate: string
}
