export type ModeId =
  "technical" | "algorithm" | "behavioral" | "stress" | "case" | "research" | "hr";

export type BackendQuestion = {
  question_id: string;
  id?: string;
  question: string;
  process_type?: string;
  role?: string;
  follow_ups?: string[];
  rubric?: string[];
  skills?: string[];
  difficulty?: string;
  source_refs?: string[];
  tests?: Array<{
    args?: unknown[];
    kwargs?: Record<string, unknown>;
    expected?: unknown;
  }>;
  source?: Record<string, unknown>;
  is_active?: boolean;
};

export type UserProfile = {
  skills: string[];
  projects: string[];
  education?: string;
  experience?: string;
  constraints?: string[];
  job_text?: string;
};

export type MatchResponse = {
  session_id: string;
  matched_skills: string[];
  questions: BackendQuestion[];
  [key: string]: unknown;
};

export type SessionSummary = {
  session_id: string;
  mode: ModeId;
  role: string;
  status?: string;
  created_at?: string;
  updated_at?: string;
  turns?: Array<Record<string, unknown>>;
  matched_skills?: string[];
  session?: {
    session_id?: string;
    mode?: ModeId;
    role?: string;
    status?: string;
    created_at?: string;
    updated_at?: string;
    [key: string]: unknown;
  };
  summary?: {
    turn_count?: number;
    average_score?: number | null;
    [key: string]: unknown;
  };
  [key: string]: unknown;
};

export type JobRecord = {
  id?: string;
  job_id?: string;
  user_id?: string;
  title?: string;
  name?: string;
  company?: string;
  role?: string;
  jd_text?: string;
  job_text?: string;
  skills?: string[];
  source_url?: string;
  source_license?: string;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
};

export type ReportRecord = {
  id?: string;
  report_id?: string;
  session_id?: string;
  title?: string;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
};

export type RequestOptions = { timeoutMs?: number; retries?: number };

export type StartSessionResponse = {
  session_id: string;
  mode: ModeId;
  role: string;
  matched_skills: string[];
  question_id: string;
  question: string;
  why_this_question: string;
  source_refs: string[];
  status: string;
  tests?: BackendQuestion["tests"];
};

export type Feedback = {
  scores: Record<string, number>;
  evidence_quotes: string[];
  strengths: string[];
  improvements: string[];
  better_answer: string;
  next_question?: string | null;
  next_action: string;
  source_refs: string[];
};

export type TurnResponse = {
  turn_id: string;
  session_id: string;
  question_id: string;
  feedback: Feedback;
  next_question?: BackendQuestion | null;
  algorithm_result?: AlgorithmResult | null;
};

export type AlgorithmResult = {
  job_id: string;
  status: "passed" | "failed" | "timeout" | "error" | "rejected" | "disabled";
  passed: number;
  total: number;
  stdout?: string;
  stderr?: string;
  runtime_ms?: number;
  details?: Array<Record<string, unknown>>;
};

export type ApiError = Error & { status?: number };

async function request<T>(
  path: string,
  init?: RequestInit,
  options: RequestOptions = {},
): Promise<T> {
  const timeoutMs = options.timeoutMs ?? 12000;
  const retries = options.retries ?? 2;
  let lastError: ApiError | null = null;
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    const controller = new AbortController();
    const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(path, {
        ...init,
        credentials: "include",
        signal: controller.signal,
        headers: {
          "Content-Type": "application/json",
          ...(init?.headers ?? {}),
        },
      });
      const raw = await response.text();
      let payload: unknown = null;
      try {
        payload = raw ? JSON.parse(raw) : null;
      } catch {
        payload = raw;
      }
      if (!response.ok) {
        const detail =
          typeof payload === "object" && payload && "detail" in payload
            ? String((payload as { detail: unknown }).detail)
            : `请求失败（${response.status}）`;
        const error = new Error(detail) as ApiError;
        error.status = response.status;
        // Retry transient HTTP failures only. 404/422 are useful contract signals
        // and should immediately fall back in the caller.
        if (
          attempt < retries &&
          (response.status === 408 || response.status === 429 || response.status >= 500)
        ) {
          lastError = error;
          await new Promise((resolve) => globalThis.setTimeout(resolve, 250 * (attempt + 1)));
          continue;
        }
        throw error;
      }
      return payload as T;
    } catch (cause) {
      const error =
        cause instanceof Error
          ? (cause as ApiError)
          : (Object.assign(new Error("网络请求失败"), {
              status: undefined,
            }) as ApiError);
      if (controller.signal.aborted) error.message = `请求超时（${timeoutMs}ms）`;
      lastError = error;
      // Non-transient HTTP failures have already been parsed above; do not
      // turn a 404/422 contract response into a multi-second retry delay.
      if (
        error.status !== undefined &&
        !(error.status === 408 || error.status === 429 || error.status >= 500)
      )
        throw error;
      if (attempt >= retries) throw error;
      await new Promise((resolve) => globalThis.setTimeout(resolve, 250 * (attempt + 1)));
    } finally {
      globalThis.clearTimeout(timeout);
    }
  }
  throw lastError || new Error("网络请求失败");
}

export function startSession(input: {
  mode: ModeId;
  role: string;
  job_text: string;
  user_profile: { skills: string[]; projects: string[] };
  difficulty?: "easy" | "medium" | "hard";
  job_id?: string;
}) {
  return request<StartSessionResponse>(
    "/api/v1/sessions",
    { method: "POST", body: JSON.stringify(input) },
    { timeoutMs: 20000, retries: 2 },
  ).then((result) => {
    rememberSession(result.session_id);
    return result;
  });
}

export function submitTurn(
  sessionId: string,
  input: {
    question_id: string;
    answer_text?: string;
    code?: string;
    language?: string;
    tests?: Array<{
      args?: unknown[];
      kwargs?: Record<string, unknown>;
      expected?: unknown;
    }>;
  },
) {
  return request<TurnResponse>(`/api/v1/sessions/${encodeURIComponent(sessionId)}/turns`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function runAlgorithm(
  sessionId: string,
  input: {
    question_id: string;
    code: string;
    language?: string;
    tests?: Array<{
      args?: unknown[];
      kwargs?: Record<string, unknown>;
      expected?: unknown;
    }>;
  },
) {
  return request<AlgorithmResult & { session_id: string; question_id: string }>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}/algorithm/run`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export function healthCheck() {
  return request<{
    status: string;
    local_model_configured: boolean;
    strong_model_configured: boolean;
  }>("/api/v1/health");
}

/** Call the persisted GraphRAG matcher for an existing session. */
export function matchSession(sessionId: string, filters: Record<string, unknown> = {}) {
  return request<MatchResponse>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}/match`,
    {
      method: "POST",
      body: JSON.stringify({ filters }),
    },
    { timeoutMs: 20000, retries: 1 },
  );
}

/** Public question-bank search; management endpoints remain admin-only. */
export async function listKnowledgeItems(
  options: { processType?: string; query?: string; limit?: number } = {},
) {
  const params = new URLSearchParams();
  if (options.processType) params.set("process_type", options.processType);
  if (options.query?.trim()) params.set("q", options.query.trim());
  params.set("limit", String(options.limit ?? 200));
  const result = await request<{ items: BackendQuestion[] }>(
    `/api/v1/questions?${params.toString()}`,
  );
  return result.items || [];
}

export function getSessionSummary(sessionId: string) {
  return request<SessionSummary>(`/api/v1/sessions/${encodeURIComponent(sessionId)}`);
}

export function completeSession(sessionId: string) {
  return request<{ status: string; session?: SessionSummary }>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}/complete`,
    { method: "POST", body: JSON.stringify({}) },
  );
}

export async function listJobs(limit = 100): Promise<JobRecord[]> {
  const result = await request<{ jobs?: JobRecord[] }>(
    `/api/v1/jobs?limit=${Math.max(1, Math.min(limit, 500))}`,
  );
  return result.jobs || [];
}

export async function listFavorites(
  limit = 500,
): Promise<{ ids: string[]; items: BackendQuestion[] }> {
  const result = await request<{ items?: BackendQuestion[] }>(
    `/api/v1/favorites?limit=${Math.max(1, Math.min(limit, 500))}`,
  );
  const items = result.items || [];
  return {
    items,
    ids: items.map((item) => item.question_id || item.id).filter((id): id is string => Boolean(id)),
  };
}

export async function listReports(limit = 100): Promise<ReportRecord[]> {
  const result = await request<{ reports?: ReportRecord[] }>(
    `/api/v1/reports?limit=${Math.max(1, Math.min(limit, 500))}`,
  );
  return result.reports || [];
}

const PROFILE_KEY = "techmatch:user-profile";
const SESSIONS_KEY = "techmatch:session-ids";
const FAVORITES_KEY = "techmatch:favorites";
const QUEUE_KEY = "techmatch:training-queue";

function readStorage<T>(key: string, fallback: T): T {
  try {
    const value = globalThis.localStorage?.getItem(key);
    return value ? (JSON.parse(value) as T) : fallback;
  } catch {
    return fallback;
  }
}
function writeStorage<T>(key: string, value: T) {
  try {
    globalThis.localStorage?.setItem(key, JSON.stringify(value));
  } catch {
    /* private mode */
  }
}
function rememberSession(sessionId: string) {
  const ids = readStorage<string[]>(SESSIONS_KEY, []);
  writeStorage(SESSIONS_KEY, [sessionId, ...ids.filter((id) => id !== sessionId)].slice(0, 50));
}
export function listRememberedSessionIds() {
  return readStorage<string[]>(SESSIONS_KEY, []);
}

export async function listSessionHistory() {
  try {
    const result = await request<{ items?: SessionSummary[] }>(
      "/api/v1/history?limit=100",
      undefined,
      { retries: 1 },
    );
    if (Array.isArray(result.items)) return result.items;
  } catch {
    // Older servers do not expose the persisted history endpoint. Fall back
    // to the locally remembered session IDs in that case.
  }
  const ids = listRememberedSessionIds();
  const results = await Promise.allSettled(ids.map((id) => getSessionSummary(id)));
  return results
    .filter((item): item is PromiseFulfilledResult<SessionSummary> => item.status === "fulfilled")
    .map((item) => item.value);
}

export function loadUserProfile(): UserProfile {
  return readStorage<UserProfile>(PROFILE_KEY, {
    skills: [],
    projects: [],
    education: "",
    experience: "",
    constraints: [],
    job_text: "",
  });
}

export async function saveUserProfile(profile: UserProfile) {
  writeStorage(PROFILE_KEY, profile);
  try {
    // The profile contract intentionally excludes free-form JD text. Persist
    // the canonical profile first, then keep the JD as a saved job record.
    await request(
      "/api/v1/profile",
      {
        method: "PUT",
        body: JSON.stringify({
          skills: profile.skills,
          projects: profile.projects,
          education: profile.education,
          experience: profile.experience,
          constraints: profile.constraints,
        }),
      },
      { retries: 0 },
    );
    if (profile.job_text?.trim()) {
      const existingJobs = await listJobs(20).catch(() => []);
      const existing = existingJobs.find((job) => (job.title || job.name) === "当前目标岗位");
      await request(
        "/api/v1/jobs",
        {
          method: "POST",
          body: JSON.stringify({
            id: existing?.id || existing?.job_id,
            title: "当前目标岗位",
            role: "当前目标岗位",
            jd_text: profile.job_text,
            skills: profile.skills,
          }),
        },
        { retries: 0 },
      );
    }
  } catch {
    /* local fallback is intentional */
  }
  return profile;
}

export function loadFavorites() {
  return readStorage<string[]>(FAVORITES_KEY, []);
}
export async function toggleFavorite(questionId: string) {
  const current = loadFavorites();
  const next = current.includes(questionId)
    ? current.filter((id) => id !== questionId)
    : [questionId, ...current];
  writeStorage(FAVORITES_KEY, next);
  try {
    const result = await request<{ favorite?: boolean }>(
      `/api/v1/questions/${encodeURIComponent(questionId)}/favorite`,
      {
        method: "POST",
        body: JSON.stringify({ favorite: next.includes(questionId) }),
      },
      { retries: 0 },
    );
    if (typeof result.favorite === "boolean" && result.favorite !== next.includes(questionId)) {
      const corrected = result.favorite
        ? [questionId, ...current.filter((id) => id !== questionId)]
        : current.filter((id) => id !== questionId);
      writeStorage(FAVORITES_KEY, corrected);
      return corrected;
    }
  } catch {
    /* endpoint is optional until user table migration lands */
  }
  return next;
}

export function queueQuestion(question: BackendQuestion) {
  writeStorage(QUEUE_KEY, question);
  return question;
}
export function takeQueuedQuestion() {
  const question = readStorage<BackendQuestion | null>(QUEUE_KEY, null);
  try {
    globalThis.localStorage?.removeItem(QUEUE_KEY);
  } catch {
    /* no-op */
  }
  return question;
}
