import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Check, Timer, Trophy } from "lucide-react";
import {
  GameState,
  Leaderboard,
  LeaderboardEntry,
  Question,
} from "../../types/game";
import { Button } from "../ui/Button";
import { Card, CardContent, CardHeader } from "../ui/Card";
import { cn } from "../../utils/cn";
import { OPTION_STYLES } from "./optionStyles";

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
  // Total questions in the quiz. Required when game finishes because
  // currentQuestion/reveal become null but we still need to display the count.
  totalQuestions?: number;
  // Number of winners to show - authoritative `Quiz.winners_count` (1/3/5/10).
  winnersCount?: number;
  /**
   * Sticky-docking offset for the control bar, so it always lands directly
   * under whatever header the host is looking at: the app shell nav is h-16,
   * the full-screen host stage header on /play is h-14.
   */
  stickyOffset?: string;
}

/** One line of the post-question scoreboard.  Every figure comes verbatim
 *  from the backend reveal/leaderboard payloads - nothing is scored here. */
interface ScoreRow {
  key: string;
  playerId: number;
  name: string;
  rank: number | null;
  answered: boolean;
  isCorrect: boolean;
  responseTimeMs: number;
  pointsAwarded: number;
  totalScore: number;
}

/** Cumulative score that counts up from last question's total to this one's. */
function CountUp({
  from,
  to,
  duration = 700,
}: {
  from: number;
  to: number;
  duration?: number;
}) {
  const [value, setValue] = useState(from);
  const frameRef = useRef<number | null>(null);

  useEffect(() => {
    const delta = to - from;
    if (delta === 0) {
      setValue(to);
      return;
    }
    const startedAt = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - startedAt) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(Math.round(from + delta * eased));
      if (t < 1) {
        frameRef.current = requestAnimationFrame(tick);
      } else {
        setValue(to);
        frameRef.current = null;
      }
    };
    frameRef.current = requestAnimationFrame(tick);
    return () => {
      if (frameRef.current !== null) {
        cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
      }
    };
  }, [from, to, duration]);

  return <>{value}</>;
}

function formatResponseTime(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return "—";
  return `${(ms / 1000).toFixed(1)}s`;
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
  totalQuestions,
  winnersCount = 3,
  stickyOffset = "top-16",
}: HostGamePanelProps) {
  const isActive = gameState === GameState.QUESTION_ACTIVE;
  const isReveal =
    gameState === GameState.QUESTION_REVEAL ||
    gameState === GameState.LEADERBOARD;
  const isFinished = gameState === GameState.FINISHED;

  // Live question while answering; after it closes we show the same question
  // merged with the reveal payload (correct answer + distribution).
  const question = isActive ? currentQuestion : currentQuestion ?? reveal;

  // Final results are shown when the game is FINISHED and we have leaderboard data.
  // This must be checked BEFORE the early return below, because currentQuestion/reveal
  // become null when the backend transitions to FINISHED.
  const isFinalResults = isFinished && !!leaderboard && leaderboard.entries.length > 0;

  // Fallback totalQuestions from prop when question is null (e.g., at FINISHED state)
  const total = question?.totalQuestions ?? totalQuestions ?? 0;
  const number = question?.questionNumber ?? 0;
  const timeLimit = question?.timeLimit ?? 20;

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

  const seconds =
    effectiveTimeRemainingMs !== null
      ? Math.max(0, Math.ceil(effectiveTimeRemainingMs / 1000))
      : null;

  const progressPct =
    effectiveTimeRemainingMs !== null && effectiveTimeRemainingMs > 0
      ? Math.min(100, (effectiveTimeRemainingMs / (timeLimit * 1000)) * 100)
      : 0;

  const correctIndex = isReveal
    ? (reveal?.correctIndex ?? question?.correctIndex)
    : undefined;
  const distribution = isReveal ? reveal?.distribution : undefined;
  const answeredCount = question?.answeredCount;
  const expired = isActive && seconds === 0;

  // ---------------------------------------------------------------
  // PER-QUESTION SCOREBOARD (host, after every question)
  //
  // Built purely from the authoritative `reveal.results` +
  // `leaderboard.entries` payloads.  The React layer never scores anything:
  // it only arranges and animates what the backend already computed.
  // ---------------------------------------------------------------
  const scoreRows = useMemo<ScoreRow[]>(() => {
    const results = reveal?.results ?? [];
    const entries = leaderboard?.entries ?? [];
    const isTeam = leaderboard?.mode === "team";

    const entryFor = (playerId: number): LeaderboardEntry | undefined => {
      if (!isTeam) {
        return entries.find((e) => (e.playerId ?? e.id) === playerId);
      }
      return entries.find((e) =>
        (e.members ?? []).some((m) => m.playerId === playerId)
      );
    };

    const rows: ScoreRow[] = results.map((r) => ({
      key: `p${r.playerId}`,
      playerId: r.playerId,
      name: r.nickname,
      rank: entryFor(r.playerId)?.rank ?? null,
      answered: true,
      isCorrect: r.isCorrect,
      responseTimeMs: r.responseTimeMs,
      pointsAwarded: r.pointsAwarded,
      totalScore: r.totalScore,
    }));

    const answered = new Set(results.map((r) => r.playerId));
    // Everyone on the roster who did not answer still gets a row, so the
    // board always accounts for every participant.
    const nonResponders: Array<{
      playerId: number;
      name: string;
      rank: number | null;
      score: number;
    }> = [];

    if (isTeam) {
      for (const entry of entries) {
        for (const member of entry.members ?? []) {
          if (answered.has(member.playerId)) continue;
          nonResponders.push({
            playerId: member.playerId,
            name: member.nickname,
            rank: entry.rank,
            score: member.score,
          });
        }
      }
    } else {
      for (const entry of entries) {
        const playerId = entry.playerId ?? entry.id;
        if (answered.has(playerId)) continue;
        nonResponders.push({
          playerId,
          name: entry.name,
          rank: entry.rank,
          score: entry.score,
        });
      }
    }

    for (const nr of nonResponders) {
      rows.push({
        key: `p${nr.playerId}`,
        playerId: nr.playerId,
        name: nr.name,
        rank: nr.rank,
        answered: false,
        isCorrect: false,
        responseTimeMs: 0,
        pointsAwarded: 0,
        totalScore: nr.score,
      });
    }

    rows.sort((a, b) => {
      if (a.rank !== null && b.rank !== null && a.rank !== b.rank) {
        return a.rank - b.rank;
      }
      if (a.rank === null && b.rank !== null) return 1;
      if (a.rank !== null && b.rank === null) return -1;
      if (b.pointsAwarded !== a.pointsAwarded) {
        return b.pointsAwarded - a.pointsAwarded;
      }
      return a.responseTimeMs - b.responseTimeMs;
    });

    return rows;
  }, [reveal, leaderboard]);

  // -----------------------------------------------------------------
  // FINAL RESULTS FLOW (manual, host-driven)
  //
  //   board     -> the COMPLETE leaderboard of every participant
  //   [SELECT WINNERS] sticky at the TOP (never auto-selected)
  //   reveal    -> bottom-to-top rank reveal, slide-up/fade/scale stagger
  //   suspense  -> drumroll
  //   winners   -> podium built from the authoritative winnersCount
  // -----------------------------------------------------------------
  type FinalPhase = "board" | "reveal" | "suspense" | "winners";
  const [finalPhase, setFinalPhase] = useState<FinalPhase>("board");
  const finalTimersRef = useRef<number[]>([]);

  const clearFinalTimers = useCallback(() => {
    for (const timer of finalTimersRef.current) {
      window.clearTimeout(timer);
    }
    finalTimersRef.current = [];
  }, []);

  useEffect(() => {
    clearFinalTimers();
    setFinalPhase("board");
    return clearFinalTimers;
  }, [isFinalResults, clearFinalTimers]);

  const finalEntries = leaderboard?.entries ?? [];

  // Winners come from the backend's `winnersCount` and are clamped to the
  // number of real participants, so a podium never shows a fabricated slot.
  const winnerCount = Math.min(
    Math.max(winnersCount || 3, 1),
    finalEntries.length
  );
  const winners = finalEntries.slice(0, winnerCount);
  // A 3+ place podium reads 2nd / 1st / 3rd left-to-right.
  const podiumOrder =
    winners.length >= 3
      ? [1, 0, 2, ...winners.slice(3).map((_, index) => index + 3)]
      : winners.map((_, index) => index);

  const startWinnerReveal = useCallback(() => {
    clearFinalTimers();
    const rows = Math.max(finalEntries.length, 1);
    const revealMs = rows * 220 + 500;
    setFinalPhase("reveal");
    finalTimersRef.current.push(
      window.setTimeout(() => setFinalPhase("suspense"), revealMs),
      window.setTimeout(() => setFinalPhase("winners"), revealMs + 1500)
    );
  }, [finalEntries.length, clearFinalTimers]);

  // The progression control docks to the top of the scroll container, so it
  // is always on screen no matter how long the scoreboard gets.
  const showNextQuestionBar =
    isReveal && !isFinalResults && hasMoreQuestions && Boolean(question);

  return (
    <div className="space-y-6">
      {/* =====================================================
          STICKY CONTROL BAR - always at the TOP, never scrolled to
      ====================================================== */}
      {showNextQuestionBar && (
        <div className={cn("sticky z-30 py-2", stickyOffset)}>
          <div className="rounded-2xl border border-purple-500/40 bg-gray-950/95 backdrop-blur px-3 py-3 shadow-lg shadow-black/50">
            <div className="flex flex-col sm:flex-row gap-3">
              <Button
                size="lg"
                onClick={onNextQuestion}
                className="flex-1 sm:flex-none sm:min-w-[280px]"
              >
                Next Question →
              </Button>

              <Button
                variant="outline"
                size="lg"
                onClick={onEndGame}
                className="flex-1 sm:flex-none"
              >
                End Quiz
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* =====================================================
          PROGRESS + TIMER (only during active gameplay)
      ====================================================== */}
      {!isFinalResults && (
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
                    : `Up to ${question?.points ?? 0} points`
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
      )}

      {/* Countdown bar (only during active gameplay) */}
      {!isFinalResults && (
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
      )}

      {/* =====================================================
          FINAL RESULTS EXPERIENCE (host only)
      ====================================================== */}
      {isFinalResults && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="space-y-6"
        >
          {/* SELECT WINNERS - sticky at the TOP, manual only */}
          {finalPhase === "board" && (
            <div className={cn("sticky z-30 py-2", stickyOffset)}>
              <Button
                size="lg"
                onClick={startWinnerReveal}
                className="w-full sm:w-auto sm:min-w-[360px] mx-auto flex items-center justify-center gap-3"
              >
                <Trophy className="w-5 h-5" />
                Select Winners
              </Button>
            </div>
          )}

          {/* QUIZ COMPLETE */}
          <div className="text-center py-6">
            <motion.h1
              initial={{ y: 20, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              className="text-4xl sm:text-5xl font-black text-white mb-2"
            >
              QUIZ COMPLETE
            </motion.h1>
            <motion.p
              initial={{ y: 10, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ delay: 0.1 }}
              className="text-lg text-gray-400"
            >
              {total} question{total === 1 ? "" : "s"} played • {playerCount}{" "}
              player{playerCount === 1 ? "" : "s"}
            </motion.p>
          </div>

          {/* COMPLETE LEADERBOARD - every participant, always first */}
          {(finalPhase === "board" ||
            finalPhase === "reveal" ||
            finalPhase === "suspense") && (
            <div key={finalPhase} className="space-y-3">
              <h2 className="text-center text-sm uppercase tracking-[0.3em] text-yellow-400 font-bold">
                {finalPhase === "board"
                  ? "Final leaderboard"
                  : "Final results"}
              </h2>

              <Card variant="outlined" className="overflow-hidden">
                <CardContent className="py-4 px-4 sm:px-6">
                  <div className="space-y-2">
                    {(finalPhase === "reveal" || finalPhase === "suspense"
                      ? finalEntries.slice().reverse()
                      : finalEntries
                    ).map((entry, position) => {
                      // Bottom-to-top reveal: the LAST place row lands first,
                      // the champion lands last for maximum suspense.
                      const delay =
                        finalPhase === "reveal" ? position * 0.22 : position * 0.05;
                      const isWinner = winners.some((w) => w.id === entry.id);

                      return (
                        <motion.div
                          key={entry.id}
                          initial={{ y: 60, opacity: 0, scale: 0.85 }}
                          animate={{ y: 0, opacity: 1, scale: 1 }}
                          transition={{
                            delay,
                            duration: finalPhase === "reveal" ? 0.45 : 0.3,
                            ease: "easeOut",
                          }}
                          className={cn(
                            "flex items-center justify-between gap-3 p-3 rounded-lg bg-gray-800/60",
                            isWinner &&
                              "bg-gradient-to-r from-yellow-500/10 to-amber-500/10 border border-yellow-500/30"
                          )}
                        >
                          <div className="flex items-center gap-3 min-w-0">
                            <motion.span
                              initial={{ scale: 0 }}
                              animate={{ scale: 1 }}
                              transition={{
                                delay: delay + 0.1,
                                type: "spring",
                                stiffness: 220,
                                damping: 15,
                              }}
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
                            </motion.span>
                            <motion.span
                              initial={{ x: -20, opacity: 0 }}
                              animate={{ x: 0, opacity: 1 }}
                              transition={{ delay: delay + 0.15 }}
                              className="font-medium truncate"
                            >
                              {entry.name}
                            </motion.span>
                          </div>
                          <motion.span
                            initial={{ x: 20, opacity: 0 }}
                            animate={{ x: 0, opacity: 1 }}
                            transition={{ delay: delay + 0.15 }}
                            className="font-bold text-purple-300 whitespace-nowrap tabular-nums"
                          >
                            {entry.score}
                          </motion.span>
                        </motion.div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {/* SUSPENSE */}
          {finalPhase === "suspense" && (
            <motion.div
              key="suspense"
              initial={{ y: 20, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              className="text-center py-6"
            >
              <motion.h3
                animate={{ scale: [1, 1.04, 1] }}
                transition={{ duration: 0.9, repeat: Infinity }}
                className="text-2xl sm:text-3xl font-bold text-yellow-300 uppercase tracking-wider"
              >
                {winnerCount === 1
                  ? "And the winner is…"
                  : `Top ${winnerCount} winners…`}
              </motion.h3>
            </motion.div>
          )}

          {/* WINNERS PODIUM - top N from the authoritative winnersCount */}
          {finalPhase === "winners" && winners.length > 0 && (
            <motion.div
              key="winners"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="space-y-4"
            >
              <motion.div
                initial={{ y: 20, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                className="text-center"
              >
                <h2 className="text-3xl sm:text-4xl font-black text-yellow-400 tracking-wider uppercase">
                  {winners.length === 1 ? "Winner" : "Winners"}
                </h2>
              </motion.div>

              <div
                className={cn(
                  "grid gap-4 items-end",
                  winners.length === 1
                    ? "grid-cols-1 max-w-md mx-auto"
                    : "grid-cols-1 sm:grid-cols-3"
                )}
              >
                {podiumOrder
                  .filter((index) => index < winners.length)
                  .map((index) => {
                    const winner = winners[index];
                    const place = index + 1;
                    return (
                      <motion.div
                        key={winner.id}
                        initial={{ scale: 0.5, y: 60, opacity: 0 }}
                        animate={{ scale: 1, y: 0, opacity: 1 }}
                        transition={{
                          type: "spring",
                          stiffness: 150,
                          damping: 13,
                          delay: index * 0.2,
                        }}
                        className={cn(
                          "relative overflow-hidden rounded-2xl border-2",
                          place === 1
                            ? "sm:min-h-[300px] bg-gradient-to-br from-yellow-500/10 via-amber-500/5 to-orange-500/10 border-yellow-500/50"
                            : place === 2
                            ? "sm:min-h-[250px] bg-gradient-to-br from-gray-400/10 via-gray-500/5 to-gray-600/10 border-gray-400/50"
                            : place === 3
                            ? "sm:min-h-[215px] bg-gradient-to-br from-amber-700/10 via-amber-800/5 to-orange-700/10 border-amber-700/50"
                            : "bg-gradient-to-br from-purple-500/10 via-indigo-500/5 to-purple-600/10 border-purple-500/40"
                        )}
                      >
                        {place === 1 && (
                          <div className="absolute inset-0 overflow-hidden pointer-events-none">
                            <motion.div
                              animate={{ rotate: 360 }}
                              transition={{
                                duration: 20,
                                repeat: Infinity,
                                ease: "linear",
                              }}
                              className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[400px] h-[400px] bg-gradient-to-r from-yellow-400/20 via-transparent to-amber-400/20 rounded-full blur-3xl"
                            />
                          </div>
                        )}

                        <div className="relative z-10 text-center space-y-3 px-4 py-6 sm:py-8">
                          <motion.span
                            animate={
                              place === 1 ? { scale: [1, 1.1, 1] } : {}
                            }
                            transition={{ duration: 1.5, repeat: Infinity }}
                            className="text-5xl block"
                          >
                            {place === 1 ? "🏆" : place === 2 ? "🥈" : place === 3 ? "🥉" : "🏅"}
                          </motion.span>

                          <p className="text-xs uppercase tracking-widest text-yellow-400 font-bold">
                            {place === 1
                              ? "Winner"
                              : place === 2
                              ? "Runner-up"
                              : place === 3
                              ? "Third place"
                              : `Place ${place}`}
                          </p>

                          <h3
                            className={cn(
                              "font-black text-white break-words",
                              place === 1
                                ? "text-3xl sm:text-5xl"
                                : "text-2xl sm:text-3xl"
                            )}
                          >
                            {winner.name}
                          </h3>

                          <p
                            className={cn(
                              "inline-flex items-center gap-2 px-4 py-2 rounded-full bg-yellow-500/20 border border-yellow-500/50 font-black text-yellow-400 tabular-nums",
                              place === 1 ? "text-2xl" : "text-lg"
                            )}
                          >
                            {winner.score} POINTS
                          </p>

                          {winner.teamName && (
                            <p className="text-sm text-gray-400">
                              Team: {winner.teamName}
                            </p>
                          )}
                        </div>
                      </motion.div>
                    );
                  })}
              </div>

              <CelebrationParticles />
            </motion.div>
          )}
        </motion.div>
      )}

      {/* =====================================================
          REGULAR QUESTION DISPLAY (not final results)
      ====================================================== */}
      {!isFinalResults && question && (
        <>
          {/* Question card */}
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

          {/* Four option cards (host view — never answerable) */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
            {question.options.map((option, index) => {
              const style = OPTION_STYLES[index % OPTION_STYLES.length];
              const Shape = style.Shape;
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
                        "w-11 h-11 sm:w-12 sm:h-12 rounded-lg grid place-items-center flex-shrink-0",
                        style.badge
                      )}
                      aria-hidden="true"
                    >
                      <Shape className="w-5 h-5 sm:w-6 sm:h-6" strokeWidth={3} />
                    </span>

                    <span className="flex-1 text-white font-semibold text-lg sm:text-xl leading-snug break-words">
                      {option}
                    </span>

                    {isReveal && isCorrect && (
                      <Check
                        className="flex-shrink-0 w-8 h-8 text-white"
                        strokeWidth={3}
                        aria-hidden="true"
                      />
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

          {/* Reveal detail */}
          {isReveal && (
            <div className="space-y-4">
              {(reveal?.correctAnswer ||
                reveal?.correctIndex !== undefined) && (
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

              {/* ----------------------------------------------------
                  PER-QUESTION SCOREBOARD
                  rank · name · +points this question · cumulative
                  count-up · correct/incorrect · response time
              ----------------------------------------------------- */}
              {scoreRows.length > 0 && (
                <Card variant="outlined">
                  <CardHeader>
                    <h3 className="text-lg font-semibold flex items-center gap-2">
                      <Timer className="w-4 h-4 text-purple-400" />
                      Question scoreboard
                    </h3>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {scoreRows.map((row, index) => (
                        <motion.div
                          key={row.key}
                          initial={{ y: 24, opacity: 0, scale: 0.96 }}
                          animate={{ y: 0, opacity: 1, scale: 1 }}
                          transition={{
                            delay: index * 0.07,
                            duration: 0.4,
                            ease: "easeOut",
                          }}
                          className="flex items-center gap-3 p-3 rounded-lg bg-gray-800/60"
                        >
                          <span
                            className={cn(
                              "w-8 h-8 rounded-full grid place-items-center text-sm font-bold flex-shrink-0",
                              row.rank === 1
                                ? "bg-yellow-500 text-black"
                                : row.rank === 2
                                ? "bg-gray-400 text-black"
                                : row.rank === 3
                                ? "bg-amber-700 text-white"
                                : "bg-gray-700 text-gray-300"
                            )}
                          >
                            {row.rank ?? "—"}
                          </span>

                          <span className="font-medium truncate flex-1 min-w-0">
                            {row.name}
                          </span>

                          <span
                            className={cn(
                              "flex-shrink-0 grid place-items-center w-7 h-7 rounded-full",
                              !row.answered
                                ? "bg-gray-700 text-gray-400"
                                : row.isCorrect
                                ? "bg-green-600 text-white"
                                : "bg-red-600 text-white"
                            )}
                            title={
                              row.answered
                                ? row.isCorrect
                                  ? "Correct"
                                  : "Incorrect"
                                : "No answer"
                            }
                          >
                            {row.answered && row.isCorrect ? (
                              <Check className="w-4 h-4" strokeWidth={3} />
                            ) : row.answered ? (
                              <span className="font-black text-xs leading-none">
                                ✕
                              </span>
                            ) : (
                              <span className="font-black text-xs leading-none">
                                –
                              </span>
                            )}
                          </span>

                          <span className="flex-shrink-0 w-16 text-right text-xs text-gray-400 tabular-nums">
                            {row.answered
                              ? formatResponseTime(row.responseTimeMs)
                              : "—"}
                          </span>

                          <span
                            className={cn(
                              "flex-shrink-0 w-20 text-right font-bold tabular-nums",
                              row.pointsAwarded > 0
                                ? "text-green-400"
                                : "text-gray-500"
                            )}
                          >
                            {row.answered
                              ? `+${row.pointsAwarded}`
                              : "+0"}
                          </span>

                          <span className="flex-shrink-0 w-24 text-right font-black text-purple-300 tabular-nums">
                            <CountUp
                              from={row.totalScore - row.pointsAwarded}
                              to={row.totalScore}
                            />
                          </span>
                        </motion.div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          {/* Host controls */}
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

          {/* The progression control lives in the sticky bar at the TOP of
              the panel, and only exists while another question follows. */}
          {isFinished && !isFinalResults && (
            <div className="p-6 rounded-2xl bg-gradient-to-r from-purple-900/40 to-indigo-900/40 border border-purple-700/50 text-center">
              <p className="text-3xl mb-2">🏁</p>
              <p className="text-xl font-bold">Quiz complete</p>
              <p className="text-sm text-gray-400 mt-1">
                {total} question{total === 1 ? "" : "s"} played.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// Simple celebration particle component
function CelebrationParticles() {
  const colors = [
    "#fbbf24",
    "#f59e0b",
    "#fb923c",
    "#f87171",
    "#a78bfa",
    "#60a5fa",
    "#34d399",
  ];

  return (
    <div
      className="fixed inset-0 pointer-events-none overflow-hidden z-50"
      aria-hidden="true"
    >
      {Array.from({ length: 30 }).map((_, i) => (
        <motion.div
          key={i}
          initial={{
            x: Math.random() * window.innerWidth,
            y: window.innerHeight + 50,
            scale: 0,
            opacity: 0,
          }}
          animate={{
            y: -100,
            x: Math.random() * window.innerWidth,
            scale: [0, 1, 0],
            opacity: [0, 1, 0],
            rotate: Math.random() * 360,
          }}
          transition={{
            delay: Math.random() * 1.5,
            duration: 2 + Math.random() * 1.5,
            ease: "easeOut",
          }}
          style={{
            position: "absolute",
            width: 8 + Math.random() * 8,
            height: 8 + Math.random() * 8,
            backgroundColor:
              colors[Math.floor(Math.random() * colors.length)],
            borderRadius: Math.random() > 0.5 ? "50%" : "4px",
            left: Math.random() * window.innerWidth,
            top: window.innerHeight + 50,
          }}
        />
      ))}
    </div>
  );
}
