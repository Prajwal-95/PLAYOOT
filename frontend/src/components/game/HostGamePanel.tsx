import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  GameState,
  Leaderboard,
  Question,
} from "../../types/game";
import { Button } from "../ui/Button";
import { Card, CardContent, CardHeader } from "../ui/Card";
import { cn } from "../../utils/cn";

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

  // ===== FINAL RESULTS STATE =====
  const isFinalResults = isFinished && leaderboard && leaderboard.entries.length > 0;

  // Get sorted entries for final leaderboard
  const finalEntries = leaderboard?.entries ?? [];

  // Winner is the first entry (already sorted by score desc)
  const winner = finalEntries[0];

  // Animation phase states
  const [phase, setPhase] = useState<"quizComplete" | "suspense" | "reveal" | "winner" | "celebration">("quizComplete");

  // Trigger animation sequence when final results appear
  useEffect(() => {
    if (isFinalResults) {
      const timer1 = setTimeout(() => setPhase("suspense"), 800);
      const timer2 = setTimeout(() => setPhase("reveal"), 1800);
      const timer3 = setTimeout(() => setPhase("winner"), 1800 + finalEntries.length * 300 + 800);
      const timer4 = setTimeout(() => setPhase("celebration"), 1800 + finalEntries.length * 300 + 1600);
      return () => {
        clearTimeout(timer1);
        clearTimeout(timer2);
        clearTimeout(timer3);
        clearTimeout(timer4);
      };
    } else {
      setPhase("quizComplete");
    }
  }, [isFinalResults, finalEntries.length]);

  return (
    <div className="space-y-6">
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
          {/* PHASE 1: QUIZ COMPLETE */}
          <AnimatePresence mode="wait">
            {phase === "quizComplete" && (
              <motion.div
                key="quizComplete"
                initial={{ scale: 0.8, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 1.2, opacity: 0 }}
                className="text-center py-12"
              >
                <motion.span
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  className="text-6xl block mb-4"
                >
                  🏁
                </motion.span>
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
                  className="text-lg text-gray-400"
                >
                  {total} question{total === 1 ? "" : "s"} played • {playerCount} player{playerCount === 1 ? "" : "s"}
                </motion.p>
              </motion.div>
            )}
          </AnimatePresence>

          {/* PHASE 2: SUSPENSE - FINAL RESULTS TITLE */}
          <AnimatePresence mode="wait">
            {(phase === "suspense" || phase === "reveal" || phase === "winner" || phase === "celebration") && (
              <motion.div
                key="finalResultsTitle"
                initial={{ y: -20, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                exit={{ y: -20, opacity: 0 }}
                className="text-center mb-6"
              >
                <motion.span
                  initial={{ scale: 0.5 }}
                  animate={{ scale: 1 }}
                  className="text-5xl block mb-2"
                >
                  📊
                </motion.span>
                <motion.h2
                  initial={{ y: 10, opacity: 0 }}
                  animate={{ y: 0, opacity: 1 }}
                  className="text-3xl sm:text-4xl font-black text-yellow-400 tracking-wider"
                >
                  FINAL RESULTS
                </motion.h2>
              </motion.div>
            )}
          </AnimatePresence>

          {/* PHASE 3: PLAYER REVEAL - Leaderboard entries from bottom to top */}
          <AnimatePresence mode="wait">
            {(phase === "reveal" || phase === "winner" || phase === "celebration") && (
              <motion.div
                key="leaderboard"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="space-y-3"
              >
                <Card variant="outlined" className="overflow-hidden">
                  <CardContent className="py-4 px-6">
                    <div className="space-y-2">
                      {/* Render entries in reverse order (bottom to top) with stagger */}
                      {finalEntries
                        .slice()
                        .reverse()
                        .map((entry, reverseIndex) => {
                          const delay = reverseIndex * 200;
                          const isWinner = entry.rank === 1;
                          // The #1 row stays hidden through the suspense
                          // phases and only lands with the winner reveal.
                          const shouldShow = !isWinner || phase === "celebration";
                          
                          return (
                            <AnimatePresence key={entry.id} mode="wait">
                              {shouldShow && (
                                <motion.div
                                  key={entry.id}
                                  initial={{ x: -50, opacity: 0 }}
                                  animate={{ x: 0, opacity: 1 }}
                                  exit={{ x: 50, opacity: 0 }}
                                  transition={{ delay, duration: 0.4, ease: "easeOut" }}
                                  className={cn(
                                    "flex items-center justify-between gap-3 p-3 rounded-lg bg-gray-800/60 transition-all",
                                    isWinner && "bg-gradient-to-r from-yellow-500/10 to-amber-500/10 border border-yellow-500/30"
                                  )}
                                >
                                  <div className="flex items-center gap-3 min-w-0">
                                    <motion.span
                                      initial={{ scale: 0 }}
                                      animate={{ scale: 1 }}
                                      transition={{ delay: delay + 100, type: "spring", stiffness: 200, damping: 15 }}
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
                                      transition={{ delay: delay + 150 }}
                                      className="font-medium truncate"
                                    >
                                      {entry.name}
                                    </motion.span>
                                  </div>
                                  <motion.span
                                    initial={{ x: 20, opacity: 0 }}
                                    animate={{ x: 0, opacity: 1 }}
                                    transition={{ delay: delay + 150 }}
                                    className="font-bold text-purple-300 whitespace-nowrap"
                                  >
                                    {entry.score}
                                  </motion.span>
                                </motion.div>
                              )}
                            </AnimatePresence>
                          );
                        })}
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            )}
          </AnimatePresence>

          {/* PHASE 4: WINNER REVEAL */}
          <AnimatePresence mode="wait">
            {winner && (phase === "winner" || phase === "celebration") && (
              <motion.div
                key="winnerReveal"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="relative"
              >
                {/* Suspense message */}
                <motion.div
                  initial={{ y: 20, opacity: 0 }}
                  animate={{ y: 0, opacity: 1 }}
                  exit={{ y: -20, opacity: 0 }}
                  transition={{ delay: 0.3 }}
                  className="text-center py-6"
                >
                  <motion.span className="text-4xl block mb-2">🥁</motion.span>
                  <motion.h3
                    initial={{ scale: 0.8 }}
                    animate={{ scale: 1 }}
                    className="text-2xl sm:text-3xl font-bold text-yellow-300 uppercase tracking-wider animate-pulse"
                  >
                    AND THE WINNER IS...
                  </motion.h3>
                </motion.div>

                {/* Winner card - only mounts when the reveal phase lands */}
                {phase === "celebration" && (
                <motion.div
                  initial={{ scale: 0.5, y: 50, opacity: 0 }}
                  animate={{ scale: 1, y: 0, opacity: 1 }}
                  transition={{ type: "spring", stiffness: 150, damping: 12 }}
                  className="relative"
                >
                  <Card
                    variant="outlined"
                    className="relative overflow-hidden bg-gradient-to-br from-yellow-500/10 via-amber-500/5 to-orange-500/10 border-2 border-yellow-500/50"
                  >
                    <CardContent className="py-10 px-6 relative">
                      {/* Confetti/decoration */}
                      <div className="absolute inset-0 overflow-hidden pointer-events-none">
                        <motion.div
                          animate={{ rotate: 360 }}
                          transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
                          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[400px] h-[400px] bg-gradient-to-r from-yellow-400/20 via-transparent to-amber-400/20 rounded-full blur-3xl"
                        />
                      </div>

                      <div className="relative z-10 text-center space-y-4">
                        <motion.span
                          animate={{ scale: [1, 1.1, 1] }}
                          transition={{ duration: 1.5, repeat: Infinity }}
                          className="text-7xl block"
                        >
                          🏆
                        </motion.span>

                        <motion.h2
                          initial={{ y: 20, opacity: 0 }}
                          animate={{ y: 0, opacity: 1 }}
                          transition={{ delay: 0.3 }}
                          className="text-sm uppercase tracking-widest text-yellow-400 font-bold"
                        >
                          WINNER
                        </motion.h2>

                        <motion.h1
                          initial={{ y: 20, opacity: 0, scale: 0.9 }}
                          animate={{ y: 0, opacity: 1, scale: 1 }}
                          transition={{ delay: 0.5, type: "spring", stiffness: 100, damping: 10 }}
                          className="text-5xl sm:text-7xl font-black text-white"
                        >
                          {winner.name}
                        </motion.h1>

                        <motion.div
                          initial={{ y: 20, opacity: 0, scale: 0.9 }}
                          animate={{ y: 0, opacity: 1, scale: 1 }}
                          transition={{ delay: 0.7, type: "spring", stiffness: 100, damping: 10 }}
                          className="inline-flex items-center gap-2 px-6 py-2 rounded-full bg-yellow-500/20 border border-yellow-500/50"
                        >
                          <span className="text-2xl">🏅</span>
                          <span className="text-2xl sm:text-3xl font-black text-yellow-400 tabular-nums">
                            {winner.score} POINTS
                          </span>
                        </motion.div>

                        {winner.teamName && (
                          <motion.p
                            initial={{ y: 10, opacity: 0 }}
                            animate={{ y: 0, opacity: 1 }}
                            transition={{ delay: 0.9 }}
                            className="text-sm text-gray-400"
                          >
                            Team: {winner.teamName}
                          </motion.p>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
                )}

                {/* Celebration particles */}
                {phase === "celebration" && (
                  <CelebrationParticles />
                )}
              </motion.div>
            )}
          </AnimatePresence>

          {/* No "Next Question" after the final question - the backend has
              already transitioned to FINISHED and the sequence above is the
              entire finale.  Existing page chrome (Dashboard / Return to Join)
              remains the way out, so no extra controls are added here. */}
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
                            width: `${playerCount > 0 ? Math.min(100, (count / playerCount) * 100) : 0}%`,
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
              {(reveal?.correctAnswer || reveal?.correctIndex !== undefined) && (
                <div className="p-4 rounded-xl bg-green-900/20 border border-green-700/50 text-center">
                  <p className="text-sm uppercase tracking-wider text-green-400 font-semibold">
                    Correct answer
                  </p>
                  <p className="text-lg font-bold text-green-200 mt-1">
                    {reveal?.correctAnswer ?? question.options[reveal?.correctIndex ?? -1]}
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

          {/* Progression controls are hidden once the backend has signalled
              there is no next question: the final question auto-finishes into
              the FINAL RESULTS sequence above (no "Next Question" button). */}
          {isReveal && !isFinalResults && hasMoreQuestions && (
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
          )}

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
  const colors = ["#fbbf24", "#f59e0b", "#fb923c", "#f87171", "#a78bfa", "#60a5fa", "#34d399"];
  
  return (
    <div className="fixed inset-0 pointer-events-none overflow-hidden z-50" aria-hidden="true">
      {Array.from({ length: 30 }).map((_, i) => (
        <motion.div
          key={i}
          initial={{ 
            x: Math.random() * window.innerWidth, 
            y: window.innerHeight + 50,
            scale: 0,
            opacity: 0
          }}
          animate={{ 
            y: -100,
            x: Math.random() * window.innerWidth,
            scale: [0, 1, 0],
            opacity: [0, 1, 0],
            rotate: Math.random() * 360
          }}
          transition={{
            delay: Math.random() * 1.5,
            duration: 2 + Math.random() * 1.5,
            ease: "easeOut"
          }}
          style={{
            position: "absolute",
            width: 8 + Math.random() * 8,
            height: 8 + Math.random() * 8,
            backgroundColor: colors[Math.floor(Math.random() * colors.length)],
            borderRadius: Math.random() > 0.5 ? "50%" : "4px",
            left: Math.random() * window.innerWidth,
            top: window.innerHeight + 50,
          }}
        />
      ))}
    </div>
  );
}