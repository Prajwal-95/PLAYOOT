/** WebSocket event types from the backend */
export enum WSEventType {
  CONNECTED = "CONNECTED",
  STATE_SYNC = "STATE_SYNC",
  PONG = "PONG",

  PLAYER_JOINED = "PLAYER_JOINED",
  PLAYER_LEFT = "PLAYER_LEFT",
  PLAYER_UPDATED = "PLAYER_UPDATED",

  TEAM_CREATED = "TEAM_CREATED",
  TEAM_JOINED = "TEAM_JOINED",
  TEAM_LEFT = "TEAM_LEFT",
  TEAM_UPDATED = "TEAM_UPDATED",

  GAME_STARTED = "GAME_STARTED",
  GAME_FINISHED = "GAME_FINISHED",
  GAME_CANCELLED = "GAME_CANCELLED",
  GAME_ERROR = "GAME_ERROR",

  QUESTION_STARTED = "QUESTION_STARTED",
  ANSWER_SUBMITTED = "ANSWER_SUBMITTED",
  PLAYER_ANSWERED = "PLAYER_ANSWERED",
  QUESTION_ENDED = "QUESTION_ENDED",
  NEXT_QUESTION = "NEXT_QUESTION",

  LEADERBOARD_UPDATED = "LEADERBOARD_UPDATED",
}

export enum WSClientAction {
  START_GAME = "START_GAME",
  NEXT_QUESTION = "NEXT_QUESTION",
  END_QUESTION = "END_QUESTION",
  END_GAME = "END_GAME",
  CANCEL_GAME = "CANCEL_GAME",
  SUBMIT_ANSWER = "SUBMIT_ANSWER",
  REQUEST_STATE = "REQUEST_STATE",
  PING = "PING",
}

export enum GameState {
  LOBBY = "LOBBY",
  QUESTION_ACTIVE = "QUESTION_ACTIVE",
  QUESTION_REVEAL = "QUESTION_REVEAL",
  LEADERBOARD = "LEADERBOARD",
  FINISHED = "FINISHED",
  CANCELLED = "CANCELLED",
}

export enum GameMode {
  INDIVIDUAL = "individual",
  TEAM = "team",
}

// Backend API response types (snake_case)
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

export interface PlayerOut {
  player_id: number;
  nickname: string;
  score: number;
  connected: boolean;
  team_id: number | null;
  team_name: string | null;
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

export interface JoinGameOut {
  player: PlayerOut;
  player_token: string;
  game: GameLookupOut;
}

// Frontend internal types (camelCase) - for convenience
export interface Game {
  gameId: number;
  gamePin: string;
  mode: string;
  state: GameState;
  hostId: number;
  hostName: string;
  quizId: number;
  quizTitle: string;
  totalQuestions: number;
  currentQuestionIndex: number;
  currentQuestionNumber: number;
  createdAt: string;
  startedAt: string | null;
}

export interface Player {
  playerId: number;
  nickname: string;
  score: number;
  connected: boolean;
  teamId: number | null;
  teamName: string | null;
  joinedAt: string;
  hasAnswered: boolean;
}

export interface Team {
  teamId: number;
  name: string;
  score: number;
  memberCount: number;
  maxSize: number;
  isFull: boolean;
  members: Player[];
  createdAt: string;
}

export interface Question {
  questionId: string;
  questionNumber: number;
  totalQuestions: number;
  question: string;
  options: string[];
  startedAt: string;
  endsAt: string;
  timeLimit: number;
  points: number;
  timeRemainingMs: number;
  serverTime: string;
  correctIndex?: number;
  correctAnswer?: string;
  explanation?: string;
  distribution?: number[];
  results?: QuestionResult[];
  answeredCount?: number;
  playerCount?: number;
  revealedAt?: string;
}

export interface QuestionResult {
  playerId: number;
  nickname: string;
  teamId: number | null;
  selectedAnswer: number;
  isCorrect: boolean;
  responseTimeMs: number;
  pointsAwarded: number;
  totalScore: number;
}

export interface LeaderboardEntry {
  rank: number;
  id: number;
  playerId?: number;
  teamId?: number;
  name: string;
  score: number;
  teamName?: string;
  connected?: boolean;
  memberCount?: number;
  members?: Player[];
  // Team stats (from backend)
  avgResponseTimeMs?: number;
  correctAnswers?: number;
  incorrectAnswers?: number;
  totalAnswers?: number;
}

export interface Leaderboard {
  mode: "individual" | "team";
  entries: LeaderboardEntry[];
  updatedAt: string;
}

export interface MyResult {
  selectedAnswer: number;
  isCorrect: boolean | null;
  responseTimeMs: number;
  pointsAwarded: number;
}

export interface GameSnapshot {
  game: Game;
  players: Player[];
  teams: Team[];
  currentQuestion: Question | null;
  reveal: Question | null;
  leaderboard: Leaderboard;
  timeRemainingMs: number | null;
  questionStartedAt: string | null;
  questionEndsAt: string | null;
  alreadyAnswered: boolean;
  myResult: MyResult | null;
  me: Player | null;
  canStart: boolean;
  serverTime: string;
}

export interface WSEnvelope<T = unknown> {
  type: string;
  timestamp: string;
  payload: T;
}

export interface ConnectedPayload {
  connectionId: string;
  role: "host" | "player";
  playerId: number | null;
  userId: number | null;
  gameId: number;
  gamePin: string;
  mode: string;
  state: GameState;
}

export interface GameErrorPayload {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface QuestionStartedPayload {
  questionId: string;
  questionNumber: number;
  totalQuestions: number;
  question: string;
  options: string[];
  startedAt: string;
  endsAt: string;
  timeLimit: number;
  points: number;
  timeRemainingMs: number;
  serverTime: string;
}

export interface AnswerSubmittedPayload {
  questionId: string;
  accepted: boolean;
  selectedAnswer: number;
  responseTimeMs: number;
  answeredCount: number;
  playerCount: number;
}

export interface PlayerAnsweredPayload {
  questionId: string;
  playerId: number;
  nickname: string;
  answeredCount: number;
  playerCount: number;
}

export interface QuestionEndedPayload {
  reason: string;
  questionId: string | null;
  questionNumber: number;
  totalQuestions: number;
  reveal: Question;
  leaderboard: Leaderboard;
  hasMoreQuestions: boolean;
  state: GameState;
}

export interface NextQuestionPayload {
  nextQuestionIndex: number;
  nextQuestionNumber: number;
  totalQuestions: number;
}

export interface GameStartedPayload {
  gameId: number;
  gamePin: string;
  mode: string;
  startedAt: string;
  totalQuestions: number;
  questions: Array<{
    questionId: string;
    questionNumber: number;
    timeLimit: number;
    points: number;
    optionCount: number;
  }>;
  lobby: LobbyOut;
}

export interface GameFinishedPayload {
  gameId: number;
  gamePin: string;
  mode: string;
  reason: string;
  endedAt: string;
  totalQuestions: number;
  playerCount: number;
  // Both leaderboard fields are HOST-ONLY: sanitize_event_for_player strips
  // them from player payloads, so they must be optional here.
  leaderboard?: Leaderboard;
  finalLeaderboard?: Leaderboard;
}

export interface GameCancelledPayload {
  gameId: number;
  gamePin: string;
  reason: string;
  cancelledAt: string;
}

export interface LobbyPayload {
  gameId: number;
  gamePin: string;
  mode: string;
  state: GameState;
  hostId: number;
  hostName: string;
  quiz: { quizId: number; title: string; questionCount: number };
  // NOTE: the WebSocket roster is camelCase (GameEngine.broadcast_lobby_state
  // -> lobby_payload), unlike the REST endpoints which return PlayerOut/TeamOut.
  players: Player[];
  teams: Team[];
  teamlessPlayers: number[];
  maxTeamSize: number;
  counts: {
    players: number;
    teams: number;
    connectedPlayers: number;
    answeredCurrent: number;
  };
  canStart: boolean;
  serverTime: string;
}

export interface PlayerPayload {
  playerId: number;
  nickname: string;
  score: number;
  connected: boolean;
  teamId: number | null;
  teamName: string | null;
  joinedAt: string;
  hasAnswered: boolean;
}

export interface TeamPayload {
  teamId: number;
  name: string;
  score: number;
  memberCount: number;
  maxSize: number;
  isFull: boolean;
  members: PlayerPayload[];
  createdAt: string;
}