import { useEffect, useState } from "react";
import {
  GameState,
  Leaderboard,
  Question,
} from "../../types/game";
import { Button } from "../ui/Button";
import { Card, CardContent, CardHeader } from "../ui/Card";
import { cn } from "../../utils/cn";

/**
 * Kahoot-style host stage.
 *
 * Everything rendered here comes from the `useGameSocket` hook, which is fed
 * exclusively by backend events - this component owns no game state of its own
 * and never advances the quiz itself.  Progression is the backend's job; the
 * host only sends `NEXT_QUESTION` / `END_QUESTION` / `END_GAME`.
 *
 * The host never answers: option cards are informational.
 */

// Kahoot's four signature option colours, in wire order.
const OPTION_STYLES = [
  {
    tile: "bg-rose-600 hover:bg-rose-500",
    badge: "bg-rose-700/60 text-white",
    shape: "■",
    bar: "bg-rose-500",
  },
  {
    tile: "bg-sky-600 hover:bg-sky-500",
    badge: "bg-sky-700/60 text-white",
    shape: "●",
    bar: "bg-sky-500",
  },
  {
    tile: "bg-amber-500 hover:bg-amber-400",
    badge: "bg-amber-600/70 text-white",
    shape: "▲",
    bar: "bg-amber-400",
  },
  {
    tile: "bg-emerald-600 hover:bg-emerald-500",
    badge: "bg-emerald-700/60 text-white",
    shape: "◆",
    bar: "bg-emerald-500",
  },
];

export interface HostGamePanelProps {
  gameState: GameState;
  currentQuestion: Question | null;
  reveal: Question | null;
  leaderboard: Leaderboard | null;
  timeRemainingMs: number | null;
  playerCount: number;
  hasMoreQuestions: boolean;
  onNextQuestion: () => void;
  onEndQuestion: () => void;
  onEndGame: () => void;
}

export function HostGamePanel({
  gameState,
  currentQuestion,
  reveal,
  leaderboard,
  timeRemainingMs,
  playerCount,
  hasMoreQuestions,
  onNextQuestion,
  onEndQuestion,
  onEndGame,
}: HostGamePanelProps) {
  const isActive = gameState === GameState.QUESTION_ACTIVE;
  const isReveal =
    gameState === GameState.QUESTION_REVEAL ||
    gameState === GameState.LEADERBOARD;
  const isFinished = gameState === GameState.FINISHED;

  // Live question while answering; after it closes we show the same question
  // merged with the reveal payload (correct answer + distribution).
  const question = isActive ? currentQuestion : currentQuestion ?? reveal;

  // Local timer fallback: if the prop updates are delayed, compute from question data
  const [localTimeRemaining, setLocalTimeRemaining] = useState<number | null>(null);

  useEffect(() => {
    // Only run local timer when actively answering and we have timing data
    if (!isActive || !question) {
      setLocalTimeRemaining(null);
      return;
    }

    const endsAt = question.endsAt;
    const serverTime = question.serverTime;
    if (!endsAt || !serverTime) {
      setLocalTimeRemaining(null);
      return;
    }

    const endsMs = Date.parse(endsAt);
    const serverMs = Date.parse(serverTime);
    if (!Number.isFinite(endsMs) || !Number.isFinite(serverMs)) {
      setLocalTimeRemaining(null);
      return;
    }

    // Calculate client-side deadline accounting for clock skew
    const deadline = Date.now() + Math.max(0, endsMs - serverMs);

    const tick = () => {
      const remaining = Math.max(0, deadline - Date.now());
      setLocalTimeRemaining(remaining);
      if (remaining === 0) {
        window.clearInterval(interval);
      }
    };

    tick();
    const interval = window.setInterval(tick, 100);
    return () => window.clearInterval(interval);
  }, [isActive, question?.endsAt, question?.serverTime]);

  // Use prop timeRemainingMs as primary, local as fallback
  const effectiveTimeRemainingMs = timeRemainingMs ?? localTimeRemaining;

  if (!question) {
    return null;
  }

  const total = question.totalQuestions;
  const number = question.questionNumber;
  const timeLimit = question.timeLimit || 20;

  const seconds =
    effectiveTimeRemainingMs !== null
      ? Math.max(0, Math.ceil(effectiveTimeRemainingMs / 1000))
      : null;

  const progressPct =
    effectiveTimeRemainingMs !== null && effectiveTimeRemainingMs > 0
      ? Math.min(100, (effectiveTimeRemainingMs / (timeLimit * 1000)) * 100)
      : 0;

  const correctIndex = isReveal
    ? (reveal?.correctIndex ?? question.correctIndex)
    : undefined;
  const distribution = isReveal ? reveal?.distribution : undefined;
  const answeredCount = question.answeredCount;
  const expired = isActive && seconds === 0;

  return (
    <div className="space-y-6">
      {/* =====================================================
          PROGRESS + TIMER
      ====================================================== */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-4 sm:gap-6">
        <div className="flex items-center gap-4 flex-1 min-w-0">
          <div
            className={cn(
              "relative flex-shrink-0 w-20 h-20 sm:w-24 sm:h-24 rounded-full grid place-items-center",
              "bg-gray-900 border-4 transition-colors",
              expired
                ? "border-red-500"
                : isActive && (seconds ?? 0) <= 5
                  ? "border-red-500 animate-pulse"
                  : isActive
                    ? "border-purple-500"
                    : "border-gray-700"
            )}
            role="timer"
          >
            <span
              className={cn(
                "text-3xl sm:text-4xl font-black tabular-nums leading-none",
                expired || (isActive && (seconds ?? 0) <= 5)
                  ? "text-red-400"
                  : "text-white"
              )}
            >
              {isActive ? (expired ? "0" : (seconds ?? "—")) : "—"}
            </span>
          </div>

          <div className="min-w-0">
            <p className="text-sm font-medium text-purple-300 uppercase tracking-wider">
              Question {number} / {total}
            </p>
            <p className="text-xs text-gray-500 mt-1">
              {isActive
                ? expired
                  ? "Time expired — closing question"
                  : `Up to ${question.points} points`
                : "Answer revealed"}
            </p>
          </div>
        </div>

        <div className="flex gap-3">
          <div className="flex-1 sm:flex-none px-4 py-3 rounded-xl bg-gray-900 border border-gray-800 text-center">
            <p className="text-2xl font-black text-white tabular-nums">
              {answeredCount ?? 0}
            </p>
            <p className="text-[11px] uppercase tracking-wider text-gray-500">
              Answered
            </p>
          </div>
          <div className="flex-1 sm:flex-none px-4 py-3 rounded-xl bg-gray-900 border border-gray-800 text-center">
            <p className="text-2xl font-black text-white tabular-nums">
              {playerCount}
            </p>
            <p className="text-[11px] uppercase tracking-wider text-gray-500">
              Players
            </p>
          </div>
        </div>
      </div>

      {/* Countdown bar */}
      <div className="h-2.5 bg-gray-800 rounded-full overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-200 ease-linear",
            expired
              ? "bg-red-500"
              : isActive
                ? (seconds ?? 0) <= 5
                  ? "bg-red-500"
                  : "bg-purple-500"
                : "bg-gray-600"
          )}
          style={{ width: `${isActive ? progressPct : 100}%` }}
        />
      </div>

      {/* =====================================================
          QUESTION
      ====================================================== */}
      <Card
        variant="outlined"
        className={cn(isReveal && "ring-2 ring-yellow-500/60")}
      >
        <CardContent className="py-6 sm:py-8">
          <h2 className="text-2xl sm:text-4xl font-bold leading-snug text-center break-words">
            {question.question}
          </h2>
        </CardContent>
      </Card>


      {/* =====================================================
          FOUR OPTION CARDS (host view — never answerable)
      ====================================================== */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
        {question.options.map((option, index) => {
          const style = OPTION_STYLES[index % OPTION_STYLES.length];
          const isCorrect =
            correctIndex !== undefined && index === correctIndex;
          const count = distribution?.[index];

          return (
            <div
              key={index}
              className={cn(
                "relative rounded-2xl border-2 border-black/20 shadow-lg overflow-hidden transition-all",
                style.tile,
                isReveal
                  ? isCorrect
                    ? "ring-4 ring-white scale-[1.01]"
                    : "opacity-45 saturate-50"
                  : "brightness-100"
              )}
            >
              <div className="flex items-center gap-4 px-5 py-5 sm:py-6 min-h-[92px]">
                <span
                  className={cn(
                    "w-11 h-11 sm:w-12 sm:h-12 rounded-lg grid place-items-center text-xl font-black flex-shrink-0",
                    style.badge
                  )}
                  aria-hidden="true"
                >
                  {style.shape}
                </span>

                <span className="flex-1 text-white font-semibold text-lg sm:text-xl leading-snug break-words">
                  {option}
                </span>

                {isReveal && isCorrect && (
                  <span className="flex-shrink-0 text-3xl" aria-hidden="true">
                    ✅
                  </span>
                )}
              </div>

              {isReveal && count !== undefined && (
                <div className="px-5 pb-4">
                  <div className="flex items-center justify-between text-xs text-white/90 mb-1">
                    <span className="uppercase tracking-wider font-semibold">
                      Responses
                    </span>
                    <span className="font-bold">{count}</span>
                  </div>
                  <div className="h-2 rounded-full bg-black/30 overflow-hidden">
                    <div
                      className={cn("h-full rounded-full", style.bar)}
                      style={{
                        width: `${
                          playerCount > 0
                            ? Math.min(100, (count / playerCount) * 100)
                            : 0
                        }%`,
                      }}
                    />
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* =====================================================
          REVEAL DETAIL
      ====================================================== */}
      {isReveal && (
        <div className="space-y-4">
          {(reveal?.correctAnswer || reveal?.correctIndex !== undefined) && (
            <div className="p-4 rounded-xl bg-green-900/20 border border-green-700/50 text-center">
              <p className="text-sm uppercase tracking-wider text-green-400 font-semibold">
                Correct answer
              </p>
              <p className="text-lg font-bold text-green-200 mt-1">
                {reveal?.correctAnswer ??
                  question.options[reveal?.correctIndex ?? -1]}
              </p>
              {reveal?.explanation && (
                <p className="text-sm text-gray-300 mt-2 italic">
                  💡 {reveal.explanation}
                </p>
              )}
            </div>
          )}

          {leaderboard && leaderboard.entries.length > 0 && (
            <Card variant="outlined">
              <CardHeader>
                <h3 className="text-lg font-semibold">
                  {leaderboard.mode === "team"
                    ? "👥 Team standings"
                    : "🏆 Standings"}
                </h3>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {leaderboard.entries.slice(0, 5).map((entry) => (
                    <div
                      key={entry.id}
                      className="flex items-center justify-between gap-3 p-3 rounded-lg bg-gray-800/60"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <span
                          className={cn(
                            "w-8 h-8 rounded-full grid place-items-center text-sm font-bold flex-shrink-0",
                            entry.rank === 1
                              ? "bg-yellow-500 text-black"
                              : entry.rank === 2
                                ? "bg-gray-400 text-black"
                                : entry.rank === 3
                                  ? "bg-amber-700 text-white"
                                  : "bg-gray-700 text-gray-300"
                          )}
                        >
                          {entry.rank}
                        </span>
                        <span className="font-medium truncate">
                          {entry.name}
                        </span>
                      </div>
                      <span className="font-bold text-purple-300 whitespace-nowrap">
                        {entry.score}
                      </span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* =====================================================
          HOST CONTROLS
      ====================================================== */}
      {isActive && (
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <Button variant="outline" size="lg" onClick={onEndQuestion}>
            ⏹ End Question Now
          </Button>
          <p className="text-xs text-gray-500 text-center sm:text-left">
            The server timer closes this question automatically.
          </p>
        </div>
      )}

      {isReveal && (
        <div className="flex flex-col sm:flex-row gap-3">
          <Button
            size="lg"
            onClick={onNextQuestion}
            disabled={!hasMoreQuestions}
            className="flex-1 sm:flex-none sm:min-w-[280px]"
          >
            {hasMoreQuestions
              ? "Next Question →"
              : "Last question played"}
          </Button>

          <Button
            variant="outline"
            size="lg"
            onClick={onEndGame}
            className="flex-1 sm:flex-none"
          >
            {hasMoreQuestions ? "End Quiz" : "🏁 Show Results"}
          </Button>
        </div>
      )}

      {isFinished && (
        <div className="p-6 rounded-2xl bg-gradient-to-r from-purple-900/40 to-indigo-900/40 border border-purple-700/50 text-center">
          <p className="text-3xl mb-2">🏁</p>
          <p className="text-xl font-bold">Quiz complete</p>
          <p className="text-sm text-gray-400 mt-1">
            {total} question{total === 1 ? "" : "s"} played.
          </p>
        </div>
      )}
    </div>
  );
}

