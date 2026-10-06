const API_BASE = import.meta.env.VITE_API_URL || "/api";

// ---------------------------------------------------------------------------
// Shared quiz limits.
//
// These mirror the backend constraints exactly so CREATE QUIZ and EDIT QUIZ
// can never drift apart, and so the UI cannot offer a value the API rejects:
//   GenerateQuizIn.question_count  -> ge=1, le=50
//   GenerateQuizIn.option_count    -> ge=2, le=6
//   QuestionIn.time_limit          -> ge=5, le=300
//   QuestionIn.points              -> ge=0, le=100000
// ---------------------------------------------------------------------------

/** Maximum questions the AI generator will accept (backend `le=50`). */
export const MAX_GENERATED_QUESTIONS = 50;
/** Minimum questions the AI generator will accept (backend `ge=1`). */
export const MIN_GENERATED_QUESTIONS = 1;

/** Supported answer options per question: 2..6 (backend `ge=2, le=6`). */
export const OPTION_COUNTS = [2, 3, 4, 5, 6] as const;
export const MIN_OPTION_COUNT = 2;
export const MAX_OPTION_COUNT = 6;

/** Timer presets - the SAME list for create and edit (seconds). */
export const TIMER_PRESETS = [5, 10, 15, 20, 30, 60, 120, 180] as const;
export const TIMER_MIN = 5;
export const TIMER_MAX = 300;

/** Base points per question - create and edit share this too. */
export const POINTS_PRESETS = [10, 20, 50, 100, 200, 500, 1000] as const;
export const POINTS_MIN = 0;
export const POINTS_MAX = 100000;

/** Clamp helper used by every numeric quiz field (never blanks the field). */
export function clampInt(raw: string, fallback: number, min: number, max: number): number {
  const parsed = Number.parseInt(raw, 10);
  if (Number.isNaN(parsed)) return fallback;
  return Math.max(min, Math.min(max, parsed));
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem("access_token");
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...options.headers,
  };

  if (token) {
    (headers as Record<string, string>)["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(error.detail?.message || error.detail || `HTTP ${res.status}`);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return res.json();
}

export const api = {
  // Auth
  register: (data: { name: string; email: string; password: string }) =>
    request<{ access_token: string; token_type: string; user: User }>("/auth/register", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  login: (data: { email: string; password: string }) =>
    request<{ access_token: string; token_type: string; user: User }>("/auth/login", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  me: () => request<User>("/auth/me"),

  // Quizzes
  listQuizzes: () => request<QuizSummary[]>("/quizzes"),

  createQuiz: (data: QuizCreateIn) =>
    request<Quiz>(`/quizzes`, { method: "POST", body: JSON.stringify(data) }),

  getQuiz: (quizId: number) => request<Quiz>(`/quizzes/${quizId}`),

  updateQuiz: (quizId: number, data: QuizUpdateIn) =>
    request<Quiz>(`/quizzes/${quizId}`, { method: "PUT", body: JSON.stringify(data) }),

  deleteQuiz: (quizId: number) =>
    request<void>(`/quizzes/${quizId}`, { method: "DELETE" }),

  generateQuiz: (data: GenerateQuizIn) =>
    request<GenerateQuizOut>(`/quizzes/generate`, { method: "POST", body: JSON.stringify(data) }),

  generateQuizFromPdf: (formData: FormData) =>
    request<GenerateQuizOut>(`/quizzes/generate/pdf`, {
      method: "POST",
      body: formData,
      headers: {}, // Let browser set Content-Type for FormData
    }),

  // Games
  createGame: (data: GameCreateIn) =>
    request<GameLookupOut>(`/games`, { method: "POST", body: JSON.stringify(data) }),

  lookupGame: (pin: string) => request<GameLookupOut>(`/games/${pin}`),

  getLobby: (pin: string) => request<LobbyOut>(`/games/${pin}/lobby`),

  listTeams: (pin: string) => request<TeamOut[]>(`/games/${pin}/teams`),

  joinGame: (pin: string, data: JoinGameIn) =>
    request<JoinGameOut>(`/games/${pin}/join`, { method: "POST", body: JSON.stringify(data) }),

  rejoinGame: (pin: string, data: JoinGameIn) =>
    request<JoinGameOut>(`/games/${pin}/rejoin`, { method: "POST", body: JSON.stringify(data) }),

  leaveGame: (pin: string, playerToken: string) =>
    request<void>(`/games/${pin}/leave`, {
      method: "POST",
      headers: { "X-Player-Token": playerToken },
    }),

  removePlayer: (pin: string, playerId: number) =>
    request<void>(`/games/${pin}/players/${playerId}`, { method: "DELETE" }),

  createTeam: (pin: string, data: TeamCreateIn, playerToken: string) =>
    request<TeamOut>(`/games/${pin}/teams`, {
      method: "POST",
      body: JSON.stringify(data),
      headers: { "X-Player-Token": playerToken },
    }),

  joinTeam: (pin: string, data: TeamJoinIn, playerToken: string) =>
    request<TeamOut>(`/games/${pin}/teams/join`, {
      method: "POST",
      body: JSON.stringify(data),
      headers: { "X-Player-Token": playerToken },
    }),

  leaveTeam: (pin: string, playerToken: string) =>
    request<void>(`/games/${pin}/teams/leave`, {
      method: "POST",
      headers: { "X-Player-Token": playerToken },
    }),

  getResults: (pin: string) => request<GameResults>(`/games/${pin}/results`),

  // Phone auth
  phoneVerify: (phoneNumber: string, firebaseToken: string) =>
    request<{ access_token: string; token_type: string; user: User }>(`/auth/phone/verify`, {
      method: "POST",
      body: JSON.stringify({ phone_number: phoneNumber, firebase_token: firebaseToken }),
    }),
};

// Types matching backend schemas
export interface User {
  id: number;
  name: string;
  email: string;
  created_at: string;
}

export interface QuizSummary {
  id: number;
  title: string;
  description: string | null;
  source_type: string;
  created_at: string;
  updated_at: string;
  question_count: number;
}

export interface QuestionIn {
  question_text: string;
  options: string[];
  correct_answer: string;
  explanation: string | null;
  time_limit: number;
  points: number;
}

export interface QuestionOut extends QuestionIn {
  id: number;
  order_index: number;
}

export interface Quiz {
  id: number;
  title: string;
  description: string | null;
  source_type: string;
  created_at: string;
  updated_at: string;
  question_count: number;
  winners_count?: 1 | 3 | 5 | 10;
  questions: QuestionOut[];
}

export interface QuizCreateIn {
  title: string;
  description: string | null;
  source_type: "topic" | "pdf" | "prompt" | "manual";
  questions: QuestionIn[];
  winners_count?: 1 | 3 | 5 | 10;
}

export interface QuizUpdateIn {
  title?: string;
  description?: string | null;
  questions?: QuestionIn[] | null;
  winners_count?: 1 | 3 | 5 | 10 | null;
}

export interface GenerateQuizIn {
  source_type: "topic" | "prompt";
  topic?: string;
  prompt?: string;
  title?: string;
  question_count: number;
  question_types: ("multiple_choice" | "multiple_answer" | "fill_blank" | "true_false")[];
  option_count: number;
  difficulty: "easy" | "medium" | "hard" | "mixed";
  time_limit: number;
  points: number;
  save: boolean;
  custom_instructions?: string;
  winners_count?: 1 | 3 | 5 | 10;
}

export interface GeneratedQuestionOut {
  question_text: string;
  question_type: "multiple_choice" | "multiple_answer" | "fill_blank" | "true_false";
  options: string[];
  correct_answer: string;
  correct_answers: string[];
  explanation: string | null;
  time_limit: number;
  points: number;
}

export interface GenerateQuizOut {
  source_type: string;
  generated_count: number;
  questions: GeneratedQuestionOut[];
  quiz: Quiz | null;
  winners_count?: 1 | 3 | 5 | 10;
}

export interface GameCreateIn {
  quiz_id: number;
  mode: "individual" | "team";
}

export interface GameLookupOut {
  game_id: number;
  game_pin: string;
  mode: string;
  status: string;
  quiz_id: number;
  quiz_title: string;
  question_count: number;
  player_count: number;
  team_count: number;
  max_team_size: number;
  joinable: boolean;
  created_at: string;
}

export interface JoinGameIn {
  nickname: string;
  team_id?: number | null;
}

export interface PlayerOut {
  player_id: number;
  nickname: string;
  score: number;
  connected: boolean;
  team_id: number | null;
  team_name: string | null;
}

export interface JoinGameOut {
  player: PlayerOut;
  player_token: string;
  game: GameLookupOut;
}

export interface TeamCreateIn {
  name: string;
  player_id?: number | null;
  join: boolean;
}

export interface TeamJoinIn {
  team_id: number;
  player_id?: number | null;
}

export interface TeamOut {
  team_id: number;
  name: string;
  score: number;
  member_count: number;
  max_size: number;
  is_full: boolean;
  members: PlayerOut[];
}

export interface LobbyOut {
  game: GameLookupOut;
  players: PlayerOut[];
  teams: TeamOut[];
}

export interface GameResults {
  // Results structure from backend
  [key: string]: unknown;
}