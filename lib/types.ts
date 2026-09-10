export type RecordData = Record<string, unknown>;
export type Dimension = { key: string; name: string; weight: number };
export type Score = { score: number | null; reason: string; basis: string; evidence_ids: string[] };
export type Assumption = { id: string; claim: string; evidence_ids: string[]; validation_method?: string; pass_threshold?: string; fail_threshold?: string; level?: string };
export type Proposal = { dimensions: Record<string, Score>; assumptions: Assumption[]; pros: string[]; cons: string[]; policy_caps: string[]; vetoes: { reason: string; confirmed: boolean; evidence_ids: string[] }[]; s_conditions: Record<string, boolean> };
export type Message = { evidence_ids?: string[]; role: string; content: string; mode?: string; field?: string; time?: string };
export type Stage = 'pre' | 'during' | 'post';
export type Coverage = { status: 'known' | 'ask' | 'unknown' | 'external' | 'future'; reason: string };
export type PilotPlan = { objective: string; scope: string; method: string; metrics: { name: string; baseline: string; target: string; measurement: string }[]; stop_conditions: string; owner: string; resources: string; cash_budget: number; internal_cost: number; max_loss: number; loss_estimate: number; planned_start: string | null; duration_days: number; checkin_after_days: number; records: string; version?: number; confirmed_at?: string; change_reason?: string };
export type StageReview = { conclusion: string; summary: string; next_action: string; next_review_days?: number | null; time: string; stage: Stage; coverage: Record<string, Coverage>; plan_version?: number };
export type Lifecycle = { stage: Stage; confirmed: boolean; paused: boolean; coverage: Record<string, Coverage>; plan?: PilotPlan | null; draft_plan?: PilotPlan | null; plan_history: PilotPlan[]; reviews: StageReview[]; review?: StageReview | null; actual_start?: string; actual_end?: string; expected_end?: string; next_review_on?: string | null; events: { action: string; reason: string; time: string; stage: Stage }[] };
export type Followup = { date: string; due: boolean; kind: string };
export type Project = { id: string; name: string; description?: string; project_type: string; version: number; messages: Message[]; last_grade?: string; updated_at: string; proposal?: Proposal; pending_patch?: RecordData; lifecycle?: Lifecycle; followup?: Followup | null; [key: string]: unknown };
export type Evidence = { id: string; title: string; source_locator: string; content: string; source_type: string; data_period: string; scope: string; verification_status: string; level: number; retrieved_at: string; repeat_verified?: boolean; valid_until?: string; conflict?: boolean };
export type Rating = { grade: string; status: string; base_score: number | null; base_grade: string | null; evidence_level: string; confidence: string; dimensions: (Score & Dimension & { weighted: number })[]; assumptions: Assumption[]; missing: string[]; triggered_rules: string[]; warnings: string[]; action: string; pros: string[]; cons: string[]; rule_version: string; resource_plan: { available_limit?: number; proposed_budget?: number | null; note?: string; formula?: string }; validation_plan: { claim: string; pass: string; fail: string; method: string }[]; reassessment_triggers: string[] };
export type Assessment = { id: string; result: Rating; created_at: string; snapshot: { company: RecordData; project: Project; evidence: Evidence[]; proposal: Proposal } };
export type Settings = { managed?: boolean; planner_model?: string; primary_model?: string | null; fallback_model?: string; reasoning_effort?: string | null; base_url: string; model: string; has_key: boolean; configured: boolean };
export type Source = { id: string; name: string; purpose: string; url: string; access: string; status: string };
export type Bootstrap = { projects: Project[]; company: RecordData; settings: Settings; sources: Source[]; dimensions: Dimension[]; types: Record<string, string>; rule_version: string };
export type Job = { id: string; project_id?: string; status: 'running' | 'success' | 'failed' | 'cancelled'; phase?: 'queued' | 'working'; result?: unknown; error?: string; partial_reply?: string };
export type Detail = { project: Project; evidence: Evidence[]; assessments: Assessment[]; active_jobs?: Job[]; initial_job?: Job | null };

export async function waitForJob<T>(id: string, onProgress?: (text: string) => void, onJob?: (job: Job) => void): Promise<T> {
  for (let count = 0; count < (onProgress ? 6000 : 900); count++) {
    const job = await api<Job>('/jobs/' + id);
    onJob?.(job);
    if (job.partial_reply !== undefined) onProgress?.(job.partial_reply);
    if (job.status !== 'running') {
      for (const key of Object.keys(localStorage)) if (key.startsWith('sabc-request-') && localStorage.getItem(key) === id) localStorage.removeItem(key);
    }
    if (job.status === 'success') return job.result as T;
    if (job.status === 'cancelled') throw new Error('已停止回答');
    if (job.status === 'failed') throw new Error(job.error || '任务失败，请检查已保存记录后重试。');
    await new Promise(resolve => setTimeout(resolve, onProgress ? 300 : 2000));
  }
  throw new Error('任务仍未完成，请重新打开项目查看状态。');
}

export async function api<T>(path: string, method = 'GET', body?: unknown, onProgress?: (text: string) => void, onJob?: (job: Job) => void): Promise<T> {
  const slow = method === 'POST' && path.match(/^\/projects\/([^/]+)\/(chat|sources\/([^/]+))$/);
  if (slow) {
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(path + JSON.stringify(body)));
    const key = 'sabc-request-' + Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('');
    const id = localStorage.getItem(key) || crypto.randomUUID();
    localStorage.setItem(key, id);
    const submitted = await api<Job>(`/projects/${slow[1]}/jobs`, 'POST', { id, operation: slow[2] === 'chat' ? 'chat' : 'source', source: slow[3] || '', payload: body });
    onJob?.(submitted);
    // A network interruption preserves the ID; retrying resumes the saved task.
    return await waitForJob<T>(id, onProgress, onJob);
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch('/api' + path, { method, signal: controller.signal, headers: body instanceof FormData ? {} : { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body) });
    const data = await response.json().catch(error => {
      if (controller.signal.aborted) throw error;
      return { detail: '服务暂时不可用，请检查启动窗口。' };
    });
    if (response.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event('sabc-session-expired'));
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '提交内容不完整，请检查输入。');
    return data as T;
  } catch (error) {
    if (controller.signal.aborted) throw new Error('连接超时。操作可能已保存，请重新打开项目核对结果；后台分析任务会继续保留，请勿重复创建项目。');
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

export function displayDate(value: string) { return new Date(value).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }); }
export function text(value: unknown) { return value === null || value === undefined ? '' : String(value); }
