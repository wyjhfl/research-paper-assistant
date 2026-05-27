function getApiBaseUrl(): string {
  const isServer = typeof window === "undefined";
  return isServer
    ? process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8091"
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8091";
}

const USER_ID_KEY = "research_user_id";
const USER_ID_RE = /^[A-Za-z0-9_\-.]{1,64}$/;

export function readCookieUserId(): string | null {
  const match = document.cookie.match(/(?:^|;\s*)research_user_id=([^;]*)/);
  const val = match?.[1];
  if (val && USER_ID_RE.test(val)) return val;
  return null;
}

export function getUserId(): string {
  if (typeof window === "undefined") return "default";
  const fromStorage = localStorage.getItem(USER_ID_KEY);
  if (fromStorage && USER_ID_RE.test(fromStorage)) return fromStorage;
  const fromCookie = readCookieUserId();
  if (fromCookie) {
    localStorage.setItem(USER_ID_KEY, fromCookie);
    return fromCookie;
  }
  return "default";
}

export function setUserId(userId: string): void {
  if (typeof window === "undefined") return;
  if (userId.trim()) {
    localStorage.setItem(USER_ID_KEY, userId.trim());
  } else {
    localStorage.removeItem(USER_ID_KEY);
  }
}

export interface HealthResponse {
  status: string;
  version: string;
  database: string;
}

export interface PaperListItem {
  id: number;
  title: string;
  filename: string;
  status: string;
  chunk_count: number;
  created_at: string;
}

export interface PaperListResponse {
  papers: PaperListItem[];
  total: number;
}

export interface PaperDetail {
  id: number;
  title: string;
  filename: string;
  status: string;
  error_message: string | null;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface ChunkExcerpt {
  id: number;
  chunk_index: number;
  text: string;
  page_start: number;
  page_end: number;
  section_title: string | null;
}

export interface PaperDetailResponse {
  paper: PaperDetail;
  chunks: ChunkExcerpt[];
}

export interface PaperUploadResponse {
  id: number;
  title: string;
  filename: string;
  status: string;
  chunk_count: number;
  job_id: string | null;
}

export interface SourceItem {
  paper_id: number;
  chunk_id: number;
  chunk_index: number;
  page_start: number;
  page_end: number;
  text_excerpt: string;
  score: number;
}

export interface AskResponse {
  answer: string;
  status: "answered" | "insufficient_context";
  confidence: number;
  sources: SourceItem[];
}

export interface EmbeddingRebuildResponse {
  paper_id: number;
  chunks_embedded: number;
  job_id: string | null;
}

export class ApiError extends Error {
  status: number;
  details?: unknown;

  constructor(status: number, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

interface FastApi422DetailItem {
  loc?: (string | number)[];
  msg?: string;
  type?: string;
}

export function parseApiError(body: unknown, status: number): ApiError {
  if (body && typeof body === "object") {
    const obj = body as Record<string, unknown>;

    if (Array.isArray(obj.detail)) {
      const items = obj.detail as FastApi422DetailItem[];
      const parts = items
        .filter((item) => item && typeof item === "object")
        .map((item) => {
          const msg = item.msg || "未知错误";
          const bodyIdx = (item.loc || []).indexOf("body");
          if (bodyIdx !== -1 && item.loc && item.loc.length > bodyIdx + 1) {
            const fieldName = String(item.loc[bodyIdx + 1]);
            return `${fieldName}: ${msg}`;
          }
          return msg;
        });
      const message = parts.length > 0
        ? `请求参数不合法：${parts.join("；")}`
        : `请求参数不合法 (${status})`;
      return new ApiError(status, message, obj.detail);
    }

    if (typeof obj.detail === "string" && obj.detail) {
      return new ApiError(status, obj.detail, obj.detail);
    }

    if (typeof obj.error === "string" && obj.error) {
      return new ApiError(status, obj.error, obj.error);
    }
  }

  if (typeof body === "string" && body) {
    return new ApiError(status, body);
  }

  return new ApiError(status, `请求失败 (${status})`);
}

export function getErrorMessage(err: unknown, fallback = "请求失败"): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  if (typeof err === "string") return err;
  return fallback;
}

async function apiFetch<T>(path: string, options?: RequestInit, userIdOverride?: string): Promise<T> {
  const baseUrl = getApiBaseUrl();
  const userId = userIdOverride ?? getUserId();
  const headers = new Headers(options?.headers);
  if (userId) {
    headers.set("X-User-Id", userId);
  }
  const fetchOptions: RequestInit = { ...options, headers, cache: "no-store", credentials: "include" };
  const res = await fetch(`${baseUrl}${path}`, fetchOptions);
  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = null;
    }
    throw parseApiError(body, res.status);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export async function fetchHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health");
}

export async function fetchPapers(userIdOverride?: string): Promise<PaperListResponse> {
  return apiFetch<PaperListResponse>("/papers", undefined, userIdOverride);
}

export async function fetchPaper(paperId: number, userIdOverride?: string): Promise<PaperDetailResponse> {
  return apiFetch<PaperDetailResponse>(`/papers/${paperId}`, undefined, userIdOverride);
}

export async function uploadPaper(file: File, asyncMode: boolean = true): Promise<PaperUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return apiFetch<PaperUploadResponse>(`/papers/upload?async_mode=${asyncMode}`, {
    method: "POST",
    body: formData,
  });
}

export async function askPaper(paperId: number, question: string): Promise<AskResponse> {
  return apiFetch<AskResponse>(`/papers/${paperId}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
}

export async function rebuildEmbeddings(paperId: number, asyncMode: boolean = true): Promise<EmbeddingRebuildResponse> {
  return apiFetch<EmbeddingRebuildResponse>(`/papers/${paperId}/embeddings/rebuild?async_mode=${asyncMode}`, {
    method: "POST",
  });
}

export interface IdeaCandidateItem {
  title: string;
  summary: string;
  research_question: string;
  method_hint: string;
  tags: string[];
  source_chunk_ids: number[];
  confidence: number;
}

export interface ExtractIdeasResponse {
  paper_id: number;
  candidates: IdeaCandidateItem[];
}

export interface IdeaSourceItem {
  paper_id: number;
  chunk_id: number;
  chunk_index: number;
  page_start: number;
  page_end: number;
  text_excerpt: string;
}

export interface SaveIdeaRequest {
  paper_id: number;
  title: string;
  summary: string;
  research_question: string;
  method_hint: string;
  tags: string[];
  source_chunk_ids: number[];
  confidence: number;
}

export interface SaveIdeaResponse {
  id: number;
  paper_id: number;
  title: string;
  summary: string;
  research_question: string;
  method_hint: string;
  tags: string[];
  confidence: number;
  status: string;
  created_at: string;
  sources: IdeaSourceItem[];
}

export interface IdeaListItem {
  id: number;
  paper_id: number;
  paper_title: string;
  title: string;
  summary: string;
  tags: string[];
  confidence: number;
  created_at: string;
  source_count: number;
}

export interface IdeaListResponse {
  ideas: IdeaListItem[];
  total: number;
}

export interface IdeaDetailResponse {
  id: number;
  paper_id: number;
  title: string;
  summary: string;
  research_question: string;
  method_hint: string;
  tags: string[];
  confidence: number;
  status: string;
  created_at: string;
  updated_at: string;
  sources: IdeaSourceItem[];
}

export async function extractIdeas(paperId: number): Promise<ExtractIdeasResponse> {
  return apiFetch<ExtractIdeasResponse>(`/papers/${paperId}/ideas/extract`, {
    method: "POST",
  });
}

export async function saveIdea(req: SaveIdeaRequest): Promise<SaveIdeaResponse> {
  return apiFetch<SaveIdeaResponse>("/ideas", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export async function fetchIdeas(userIdOverride?: string): Promise<IdeaListResponse> {
  return apiFetch<IdeaListResponse>("/ideas", undefined, userIdOverride);
}

export async function fetchIdea(ideaId: number, userIdOverride?: string): Promise<IdeaDetailResponse> {
  return apiFetch<IdeaDetailResponse>(`/ideas/${ideaId}`, undefined, userIdOverride);
}

export async function deleteIdea(ideaId: number): Promise<void> {
  await apiFetch<void>(`/ideas/${ideaId}`, {
    method: "DELETE",
  });
}

export interface AgentRunRequest {
  task_type: "summarize_paper" | "extract_ideas" | "recommend_citations" | "recommend_citations_multi";
  paper_id?: number;
  paper_ids?: number[];
  question?: string;
  draft_text?: string;
}

export interface AgentRunResponse {
  run_id: string;
  status: string;
  task_type: string;
  output: Record<string, unknown>;
  warnings: string[];
  confidence: number;
}

export interface AgentRunDetailResponse {
  run_id: string;
  task_type: string;
  status: string;
  paper_id: number | null;
  input: Record<string, unknown>;
  output: Record<string, unknown> | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export async function runAgent(req: AgentRunRequest): Promise<AgentRunResponse> {
  return apiFetch<AgentRunResponse>("/agent/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export async function fetchAgentRun(runId: string): Promise<AgentRunDetailResponse> {
  return apiFetch<AgentRunDetailResponse>(`/agent/runs/${runId}`);
}

export interface MultiPaperSourceItem {
  paper_id: number;
  paper_title: string;
  chunk_id: number;
  chunk_index: number;
  page_start: number;
  page_end: number;
  text_excerpt: string;
  score: number;
}

export interface MultiPaperAskResponse {
  answer: string;
  status: "answered" | "insufficient_context";
  confidence: number;
  sources: MultiPaperSourceItem[];
}

export interface PaperSearchResponse {
  results: MultiPaperSourceItem[];
}

export async function multiPaperAsk(
  question: string,
  paperIds?: number[],
  topK: number = 8,
): Promise<MultiPaperAskResponse> {
  return apiFetch<MultiPaperAskResponse>("/papers/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, paper_ids: paperIds || null, top_k: topK }),
  });
}

export async function searchPaperChunks(
  query: string,
  paperIds?: number[],
  topK: number = 10,
): Promise<PaperSearchResponse> {
  return apiFetch<PaperSearchResponse>("/papers/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, paper_ids: paperIds || null, top_k: topK }),
  });
}

export interface ModelCallEvent {
  id: number;
  operation: string;
  provider: string;
  model: string;
  status: string;
  duration_ms: number;
  input_count: number;
  input_chars: number;
  output_chars: number;
  error_type: string | null;
  error_message: string | null;
  metadata_json: string | null;
  created_at: string;
}

export interface ModelCallListResponse {
  events: ModelCallEvent[];
  total: number;
}

export interface ModelCallSummaryResponse {
  total_calls: number;
  success_calls: number;
  failed_calls: number;
  avg_duration_ms: number;
  calls_by_operation: Record<string, number>;
  calls_by_provider: Record<string, number>;
}

export async function fetchModelCalls(
  limit: number = 50,
  operation?: string,
  status?: string,
  provider?: string,
): Promise<ModelCallListResponse> {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  if (operation) params.set("operation", operation);
  if (status) params.set("status", status);
  if (provider) params.set("provider", provider);
  return apiFetch<ModelCallListResponse>(`/usage/model-calls?${params.toString()}`);
}

export async function fetchModelCallSummary(
  operation?: string,
  provider?: string,
): Promise<ModelCallSummaryResponse> {
  const params = new URLSearchParams();
  if (operation) params.set("operation", operation);
  if (provider) params.set("provider", provider);
  const qs = params.toString();
  return apiFetch<ModelCallSummaryResponse>(`/usage/model-calls/summary${qs ? `?${qs}` : ""}`);
}

export interface EvalCaseSummary {
  case_id: string;
  type: string;
  severity: string;
  status: string;
  duration_ms: number;
  warnings: string[];
}

export interface EvalReportMetadata {
  llm_model: string;
  embedding_model: string;
  embedding_dimension: number;
  case_file: string;
}

export interface EvalReportTotals {
  total: number;
  passed: number;
  warning: number;
  failed: number;
  blocker_failed: number;
}

export interface EvalReportTrend {
  previous_report_count: number;
  previous_latest_timestamp: string | null;
  passed_delta: number;
  warning_delta: number;
  failed_delta: number;
}

export interface EvalReportSummaryResponse {
  timestamp: string;
  can_proceed: boolean;
  metadata: EvalReportMetadata;
  totals: EvalReportTotals;
  trend: EvalReportTrend;
  cases: EvalCaseSummary[];
}

export async function fetchLatestEvalReport(): Promise<EvalReportSummaryResponse | null> {
  try {
    return await apiFetch<EvalReportSummaryResponse>("/usage/eval-report/latest");
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      return null;
    }
    throw err;
  }
}

export interface AuthUserResponse {
  user_id: string;
  email: string;
  display_name: string | null;
  created_at?: string;
  auth_mode?: string;
}

export async function authRegister(email: string, password: string, displayName?: string): Promise<AuthUserResponse> {
  return apiFetch<AuthUserResponse>("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, display_name: displayName || null }),
  });
}

export async function authLogin(email: string, password: string): Promise<AuthUserResponse> {
  return apiFetch<AuthUserResponse>("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export async function authLogout(): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>("/auth/logout", {
    method: "POST",
  });
}

export async function authMe(): Promise<AuthUserResponse | null> {
  try {
    return await apiFetch<AuthUserResponse>("/auth/me");
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      return null;
    }
    throw err;
  }
}

export interface JobItem {
  job_id: string;
  job_type: string;
  status: string;
  input_summary: string | null;
  output_summary: string | null;
  error_message: string | null;
  progress_current: number;
  progress_total: number;
  attempts: number;
  max_attempts: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface JobListResponse {
  jobs: JobItem[];
  total: number;
}

export async function fetchJobs(
  status?: string,
  jobType?: string,
  limit: number = 50,
): Promise<JobListResponse> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (jobType) params.set("job_type", jobType);
  params.set("limit", String(limit));
  const qs = params.toString();
  return apiFetch<JobListResponse>(`/jobs${qs ? `?${qs}` : ""}`);
}

export async function fetchJob(jobId: string): Promise<JobItem> {
  return apiFetch<JobItem>(`/jobs/${jobId}`);
}

export async function createJob(
  jobType: string,
  input: Record<string, unknown> = {},
  maxAttempts: number = 1,
): Promise<JobItem> {
  return apiFetch<JobItem>("/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_type: jobType, input, max_attempts: maxAttempts }),
  });
}

export async function cancelJob(jobId: string): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(`/jobs/${jobId}/cancel`, {
    method: "POST",
  });
}

export interface WorkerHealth {
  worker_enabled: boolean;
  poll_interval_seconds: number;
  max_attempts_default: number;
  stale_running_seconds: number;
  running_count: number;
  pending_count: number;
  failed_count: number;
  stale_running_count: number;
}

export async function fetchWorkerHealth(): Promise<WorkerHealth> {
  return apiFetch<WorkerHealth>("/jobs/worker/health");
}

export async function retryJob(jobId: string): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(`/jobs/${jobId}/retry`, {
    method: "POST",
  });
}

export interface StorageSummary {
  paper_count: number;
  chunk_count: number;
  storage_bytes: number;
  failed_paper_count: number;
}

export async function fetchStorageSummary(): Promise<StorageSummary> {
  return apiFetch<StorageSummary>("/usage/storage-summary");
}
