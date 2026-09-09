export type RecordData = Record<string, unknown>;
export type Dimension = { key: string; name: string; weight: number };
export type Score = { score: number | null; reason: string; basis: string; evidence_ids: string[] };
export type Assumption = { id: string; claim: string; evidence_ids: string[]; validation_method?: string; pass_threshold?: string; fail_threshold?: string; level?: string };
export type Proposal = { dimensions: Record<string, Score>; assumptions: Assumption[]; pros: string[]; cons: string[]; policy_caps: string[]; vetoes: { reason: string; confirmed: boolean; evidence_ids: string[] }[]; s_conditions: Record<string, boolean> };
export type Message = { role: string; content: string; mode?: string; field?: string; time?: string };
export type Project = { id: string; name: string; description?: string; project_type: string; version: number; messages: Message[]; last_grade?: string; updated_at: string; proposal?: Proposal; pending_patch?: RecordData; [key: string]: unknown };
export type Evidence = { id: string; title: string; source_locator: string; content: string; source_type: string; data_period: string; scope: string; verification_status: string; level: number; retrieved_at: string; repeat_verified?: boolean; valid_until?: string; conflict?: boolean };
export type Rating = { grade: string; status: string; base_score: number | null; base_grade: string | null; evidence_level: string; confidence: string; dimensions: (Score & Dimension & { weighted: number })[]; assumptions: Assumption[]; missing: string[]; triggered_rules: string[]; warnings: string[]; action: string; pros: string[]; cons: string[]; rule_version: string; resource_plan: { available_limit?: number; proposed_budget?: number | null; note?: string; formula?: string }; validation_plan: { claim: string; pass: string; fail: string; method: string }[]; reassessment_triggers: string[] };
export type Assessment = { id: string; result: Rating; created_at: string; snapshot: { company: RecordData; project: Project; evidence: Evidence[]; proposal: Proposal } };
export type Settings = { base_url: string; model: string; has_key: boolean; configured: boolean };
export type Source = { id: string; name: string; purpose: string; url: string; access: string; status: string };
export type Bootstrap = { projects: Project[]; company: RecordData; settings: Settings; sources: Source[]; dimensions: Dimension[]; types: Record<string, string>; rule_version: string };
export type Detail = { project: Project; evidence: Evidence[]; assessments: Assessment[] };

export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch('/api' + path, { method, headers: body instanceof FormData ? {} : { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body) });
  const data = await response.json().catch(() => ({ detail: '服务暂时不可用，请检查启动窗口。' }));
  if (response.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event('sabc-session-expired'));
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '提交内容不完整，请检查输入。');
  return data as T;
}

export function displayDate(value: string) { return new Date(value).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }); }
export function text(value: unknown) { return value === null || value === undefined ? '' : String(value); }
