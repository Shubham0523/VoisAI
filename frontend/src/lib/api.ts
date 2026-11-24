export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const USER_KEY = "voisai.user_id";

export function getUserId(): string | null {
  try {
    return localStorage.getItem(USER_KEY);
  } catch {
    return null;
  }
}

function saveUserId(id: string) {
  try {
    localStorage.setItem(USER_KEY, id);
  } catch {
    /* private mode: identity just won't persist */
  }
}

/** The free API host sleeps when idle and takes up to a minute to wake. Ping it as soon as the
 * page opens so it's warm by the time the learner presses "Start talking". */
export async function wakeApi(signal?: AbortSignal): Promise<void> {
  for (let i = 0; i < 30; i++) {
    try {
      const res = await fetch(`${API_URL}/api/health`, { signal, cache: "no-store" });
      if (res.ok) return;
    } catch (e) {
      if (signal?.aborted) throw e;
    }
    await new Promise((r) => setTimeout(r, 3000));
  }
  throw new Error("server did not wake up");
}

export type Connection = { serverUrl: string; token: string; room: string; userId: string };

export async function fetchConnection(): Promise<Connection> {
  const res = await fetch(`${API_URL}/api/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: getUserId() }),
  });
  if (!res.ok) throw new Error(`token request failed: ${res.status} ${await res.text()}`);
  const d = await res.json();
  saveUserId(d.user_id);
  return { serverUrl: d.server_url, token: d.token, room: d.room, userId: d.user_id };
}

export type SkillRow = {
  skill_id: string;
  name: string;
  area: string;
  mastery: number;
  low: number;
  high: number;
  evidence: number;
  status: "unknown" | "weak" | "developing" | "mastered";
};

export type SessionMetrics = {
  user_turns: number;
  user_words: number;
  errors: number;
  errors_per_100w: number | null;
  target_accuracy: number | null;
  mattr: number | null;
  mean_utterance_len: number | null;
  subordination_rate: number | null;
  wpm: number | null;
  fillers_per_100w: number | null;
  words_used: string[];
  target_skills: string[];
  benchmark: boolean;
  cefr: string | null;
};

export type Recap = {
  polish?: { skill: string; you_said: string; natural: string };
  win?: { skill: string; times: number };
  word?: { word: string; meaning: string; you_used_it: boolean };
};

export type SessionRow = {
  n: number;
  id: string;
  started_at: string;
  metrics: SessionMetrics | null;
  recap: Recap | null;
  summary: string | null;
  targets: string[];
  rationale: string | null;
};

export type Progress = {
  user: { id: string; name: string; native_language: string; is_simulated: boolean; level: string | null };
  sessions: SessionRow[];
  skills: SkillRow[];
  skill_history: Record<string, (number | null)[]>;
  vocab: { word: string; status: string; times_used: number; meaning: string | null }[];
  benchmarks: { session: number; date: string; text: string; metrics: SessionMetrics | null }[];
};

export type UserRow = {
  id: string;
  name: string;
  native_language: string;
  is_simulated: boolean;
  level: string | null;
  sessions: number;
};

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json();
}

export const fetchProgress = (userId: string) =>
  getJson<Progress>(`/api/users/${encodeURIComponent(userId)}/progress`);
export const fetchUsers = () => getJson<UserRow[]>("/api/users");

export type PRF = { tp: number; fp: number; fn: number; precision: number | null; recall: number | null };
export type EvalLearner = {
  name: string;
  level: string;
  l1: string;
  planted: Record<string, number>;
  score: {
    analyst: { overall: PRF; per_skill: Record<string, PRF> };
    planner: { sessions_targeting_a_planted_skill: number; planted_share_of_targets: number };
    friend: {
      replies: number;
      teacher_leak_rate: number | null;
      leaks: { reply: string; match: string }[];
      recast_rate: number | null;
      modeled_within_2_rate?: number | null;
    };
  };
  true_rates: Record<string, number>[];
  targets: string[][];
  metrics: SessionMetrics[];
};
export type EvalRun = { planner: string; sessions: number; turns: number; learners: Record<string, EvalLearner> };
export const fetchEval = () => getJson<Record<string, EvalRun>>("/api/eval");
