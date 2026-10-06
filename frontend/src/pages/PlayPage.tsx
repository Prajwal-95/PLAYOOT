import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { useGameSocket } from "../hooks/useGameSocket";
import { GameState } from "../types/game";
import { Button } from "../components/ui/Button";
import { Card, CardHeader, CardContent, CardFooter } from "../components/ui/Card";
import { HostGamePanel } from "../components/game/HostGamePanel";
import { cn } from "../utils/cn";
import { formatDistanceToNow } from "date-fns";

// Kahoot's four signature option colours, in wire order.
const OPTION_TILES = [
  { tile: "bg-rose-600", shape: "â– " },
  { tile: "bg-sky-600", shape: "â—" },
  { tile: "bg-amber-500", shape: "â–²" },
  { tile: "bg-emerald-600", shape: "â—†" },
] as const;

export function PlayPage() {
  const { gamePin } = useParams<{ gamePin: string }>();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [showReconnect, setShowReconnect] = useState(false);
  const questionStartRef = useRef<number | null>(null);

  const playerToken = gamePin ? (localStorage.getItem(`player_token_${gamePin}`) ?? undefined) : undefined;

  // Keep this callback stable so the WebSocket hook does not tear the socket
  // down and rebuild it on every render.  `useGameSocket` chains this into
  // handleMessage -> connect -> the connect-on-mount effect, so a fresh
  // function identity on each render closes the socket mid-handshake and
  // reconnects, which the browser reports as code 1006.
  const handleSocketError = useCallback((err: { message?: string; code?: string }) => {
    setError(err?.message || "WebSocket error");
    if (err?.code === "QUESTION_EXPIRED" || err?.code === "ALREADY_ANSWERED") {
      // These are non-fatal
    } else if (
      err?.code === "GAME_ENDED" ||
      err?.code === "GAME_CANCELLED" ||
      err?.code === "PLAYER_NOT_IN_GAME"
    ) {
      setShowReconnect(false);
    }
  }, []);

  console.log("[PLAYER GAME] mounting", {
    gamePin,
    hasPlayerToken: Boolean(playerToken),
  });

  const {
    connected,
    connecting,
    role,
    game,
    currentQuestion,
    reveal,
    leaderboard,
    players,
    timeRemainingMs,
    hasMoreQuestions,
    alreadyAnswered,
    myResult,
    me,
    submitAnswer,
    requestState,
    disconnect,
    reconnect,
    nextQuestion,
    endQuestion,
    endGame,
  } = useGameSocket({
    gamePin: gamePin || "",
    playerToken,
    onError: handleSocketError,
  });

  console.log("[PLAYER GAME] useGameSocket enabled", {
    gamePin,
    hasPlayerToken: Boolean(playerToken),
    connected,
    connecting,
  });

  // Handle reconnection
  useEffect(() => {
    if (!connected && !connecting && playerToken && !showReconnect) {
      setShowReconnect(true);
    }
    if (connected) {
      setShowReconnect(false);
    }
  }, [connected, connecting, playerToken, showReconnect]);

  // Request state on connect
  useEffect(() => {
    if (connected) {
      requestState();
    }
  }, [connected, requestState]);

  const handleAnswer = (answerIndex: number) => {
    if (!currentQuestion || alreadyAnswered) return;
    submitAnswer(currentQuestion.questionId, answerIndex);
  };

  const handleRejoin = () => {
    reconnect();
  };

  const handleLeave = () => {
    if (confirm("Leave this game? You won't be able to rejoin unless the host allows it.")) {
      disconnect();
      localStorage.removeItem(`player_token_${gamePin}`);
      navigate("/join");
    }
  };

  if (!gamePin) {
    return <div className="min-h-screen flex items-center justify-center">Loading...</div>;
  }

  // Waiting in lobby
  if (game && game.state === GameState.LOBBY) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <Card className="w-full max-w-md text-center">
          <CardContent className="py-12">
            <div className="text-6xl mb-4">ðŸŽ®</div>
            <h1 className="text-2xl font-bold mb-2">Waiting for Host</h1>
            <p className="text-gray-400 mb-6">The game will start when the host begins</p>
            <div className="flex items-center justify-center gap-2 text-sm text-gray-500">
              <span className={cn("w-2 h-2 rounded-full", connected ? "bg-green-400" : "bg-gray-600")} />
              <span>{connected ? "Connected" : "Connecting..."}</span>
            </div>
            {me && (
              <div className="mt-6 p-4 bg-gray-800/50 rounded-lg text-left">
                <p className="text-sm text-gray-500">Your Nickname</p>
                <p className="font-medium">{me.nickname}</p>
              </div>
            )}
            <Button variant="outline" onClick={handleLeave} className="mt-6 w-full">
              Leave Game
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Game cancelled/finished — PLAYER view only.
  //
  // Role-based, never device-based: the WebSocket `role` decides. A host on
  // this route falls through to the host stage below and gets the full final
  // results presentation instead.
  if (
    game &&
    role !== "host" &&
    (game.state === GameState.CANCELLED || game.state === GameState.FINISHED)
  ) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <Card className="w-full max-w-md text-center">
          <CardContent className="py-12">
            {game.state === GameState.FINISHED ? (
              // PLAYER END SCREEN - role-based, no score data of any kind.
              // The backend never sends leaderboard/scores/ranking to player
              // sockets (sanitize_event_for_player), so there is nothing
              // score-related on this screen by construction.
              <div className="space-y-6">
                <motion.div
                  initial={{ scale: 0.7, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ type: "spring", stiffness: 150, damping: 15 }}
                  className="space-y-5"
                >
                  <motion.span
                    initial={{ y: -20, opacity: 0 }}
                    animate={{ y: 0, opacity: 1 }}
                    transition={{ delay: 0.2 }}
                    className="text-7xl block"
                  >
                    🎉
                  </motion.span>

                  <motion.h1
                    initial={{ y: 20, opacity: 0 }}
                    animate={{ y: 0, opacity: 1 }}
                    transition={{ delay: 0.35 }}
                    className="text-4xl sm:text-5xl font-black text-white"
                  >
                    QUIZ COMPLETE
                  </motion.h1>

                  <motion.div
                    initial={{ y: 20, opacity: 0 }}
                    animate={{ y: 0, opacity: 1 }}
                    transition={{ delay: 0.55 }}
                    className="mt-6 p-6 rounded-xl bg-gradient-to-br from-purple-900/30 to-indigo-900/30 border border-purple-500/30"
                  >
                    <p className="text-lg text-gray-300 leading-relaxed">
                      See the host screen
                      <br />
                      for the final results
                    </p>
                  </motion.div>
                </motion.div>

                <Button variant="outline" onClick={handleLeave} className="w-full">
                  Return to Join
                </Button>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="text-6xl mb-4">🚫</div>
                <h1 className="text-2xl font-bold mb-2">Game Cancelled</h1>
                <p className="text-gray-400 mb-6">The host cancelled the game.</p>
                <Button variant="outline" onClick={handleLeave} className="w-full">
                  Return to Join
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    );
  }

  // Question active or reveal/leaderboard
  const displayQuestion = currentQuestion || reveal;
  const expired =
    game?.state === GameState.QUESTION_ACTIVE &&
    timeRemainingMs !== null &&
    timeRemainingMs <= 0;
  const isAnswering =
    game?.state === GameState.QUESTION_ACTIVE &&
    Boolean(displayQuestion) &&
    !alreadyAnswered &&
    !expired;
  const isRevealing = game?.state === GameState.QUESTION_REVEAL && reveal;
  const isLeaderboard = game?.state === GameState.LEADERBOARD && leaderboard;

  if (!displayQuestion && !isLeaderboard) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <Card className="w-full max-w-md text-center">
          <CardContent className="py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-4 border-purple-600 border-t-transparent mx-auto" />
            <p className="text-gray-400 mt-4">Loading game...</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ------------------------------------------------------------------
  // ROLE-BASED RENDERING
  // ------------------------------------------------------------------
  // The WebSocket `role` decides the interface, never the device.  A host that
  // lands on this route gets the host stage; a laptop player still gets the
  // four answer buttons below.
  if (role === "host") {
    return (
      <div className="min-h-screen bg-gray-950">
        <header className="border-b border-gray-800 bg-gray-900/80 backdrop-blur-sm sticky top-0 z-50">
          <div className="max-w-5xl mx-auto px-4">
            <div className="flex items-center justify-between h-14 gap-2">
              <div className="flex items-center gap-2 sm:gap-3 min-w-0">
                <span className="text-xl flex-shrink-0">ðŸŽ®</span>
                <h1 className="font-bold text-base sm:text-lg truncate">
                  {game?.quizTitle || "PLAYOOT"}
                </h1>
                <span className="px-2 py-0.5 text-xs font-medium rounded bg-gray-800 text-gray-400 flex-shrink-0 whitespace-nowrap">
                  PIN: {gamePin}
                </span>
              </div>
              <div
                className={cn(
                  "w-3 h-3 rounded-full",
                  connected ? "bg-green-400" : "bg-red-400"
                )}
              />
            </div>
          </div>
        </header>

        <main className="max-w-5xl mx-auto px-4 py-6">
          <HostGamePanel
            gameState={game?.state ?? GameState.LOBBY}
            currentQuestion={currentQuestion}
            reveal={reveal}
            leaderboard={leaderboard}
            timeRemainingMs={timeRemainingMs}
            playerCount={players.length}
            hasMoreQuestions={hasMoreQuestions}
            onNextQuestion={nextQuestion}
            onEndQuestion={endQuestion}
            onEndGame={endGame}
          />
        </main>
      </div>
    );
  }

  // Calculate progress for timer
  const timeLimit = displayQuestion?.timeLimit || 20;
  const progress = timeRemainingMs !== null && timeRemainingMs > 0 
    ? (timeRemainingMs / (timeLimit * 1000)) * 100 
    : 0;

  return (
    <div className="min-h-screen bg-gray-950">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-900/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-4xl mx-auto px-4">
          <div className="flex items-center justify-between h-14 gap-2">
            <div className="flex items-center gap-2 sm:gap-3 min-w-0">
              <span className="text-xl flex-shrink-0">ðŸŽ®</span>
              <h1 className="font-bold text-base sm:text-lg truncate">{game?.quizTitle || "PLAYOOT"}</h1>
              <span className="px-2 py-0.5 text-xs font-medium rounded bg-gray-800 text-gray-400 flex-shrink-0 whitespace-nowrap">
                PIN: {gamePin}
              </span>
            </div>
            <div className="flex items-center gap-3">
              {me && (
                <div className="text-right hidden sm:block">
                  <p className="text-xs text-gray-500">{me.nickname}</p>
                </div>
              )}
              <div className={cn(
                "w-3 h-3 rounded-full",
                connected ? "bg-green-400" : "bg-red-400"
              )} />
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-6">
        {/* Timer Bar */}
        {(game?.state === GameState.QUESTION_ACTIVE || game?.state === GameState.QUESTION_REVEAL) && (
          <div className="mb-6">
            <div className="flex items-center justify-between text-sm mb-1">
              <span className="text-gray-400">Question {displayQuestion?.questionNumber} of {displayQuestion?.totalQuestions}</span>
              <span className={cn(
                "font-mono font-bold",
                timeRemainingMs !== null && timeRemainingMs < 5000 ? "text-red-400 animate-pulse" : "text-purple-400"
              )}>
                {timeRemainingMs !== null ? `${Math.ceil(timeRemainingMs / 1000)}s` : "â€”"}
              </span>
            </div>
            <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
              <div 
                className={cn(
                  "h-full rounded-full transition-all duration-300 ease-linear",
                  timeRemainingMs !== null && timeRemainingMs < 5000 ? "bg-red-500" : "bg-purple-500"
                )}
                style={{ width: `${Math.max(0, progress)}%` }}
              />
            </div>
          </div>
        )}

        {/* ANSWER GRID -------------------------------------------------
            Role/device note: this is the PLAYER stage.  The question text and
            image are deliberately never rendered here â€” only four large
            touch targets, and one tap locks the choice in. */}
        {displayQuestion && (
          <div className="mb-6 space-y-4">
            {/* Progress only â€” no question text. */}
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold uppercase tracking-wider text-purple-300">
                Question {displayQuestion.questionNumber} /{" "}
                {displayQuestion.totalQuestions}
              </p>
              <p
                className={cn(
                  "text-lg font-black font-mono tabular-nums",
                  expired ? "text-red-400" : "text-gray-300"
                )}
              >
                {expired
                  ? "â± Time up"
                  : isRevealing || isLeaderboard
                    ? "âœ… Revealed"
                    : timeRemainingMs === null
                      ? "â€”"
                      : `${Math.max(
                          0,
                          Math.ceil(timeRemainingMs / 1000)
                        )}s`}
              </p>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {displayQuestion.options.map((option, index) => {
                const tile =
                  OPTION_TILES[index % OPTION_TILES.length];
                const isCorrect = Boolean(
                  isRevealing &&
                    reveal &&
                    index === reveal.correctIndex
                );
                const isSelected =
                  myResult?.selectedAnswer === index;
                const locked = !isAnswering;

                let stateClass = "";
                if (isCorrect) {
                  stateClass = "ring-4 ring-white brightness-110";
                } else if (isSelected && isRevealing) {
                  stateClass = "ring-4 ring-red-300 brightness-75";
                } else if (isSelected) {
                  stateClass = "ring-4 ring-white brightness-110";
                } else if (locked) {
                  stateClass = "opacity-40 saturate-50";
                }

                return (
                  <button
                    key={index}
                    type="button"
                    onClick={() => handleAnswer(index)}
                    disabled={!isAnswering}
                    aria-pressed={isSelected}
                    className={cn(
                      "relative w-full min-h-[84px] rounded-2xl px-5 py-5",
                      "flex items-center gap-4 text-left",
                      "border-2 border-black/20 shadow-lg overflow-hidden",
                      "transition-all duration-150 active:scale-[0.98]",
                      "focus:outline-none focus:ring-4 focus:ring-purple-400",
                      "disabled:cursor-default",
                      tile.tile,
                      stateClass
                    )}
                  >
                    <span
                      className="w-10 h-10 rounded-lg bg-black/25 grid place-items-center text-lg font-black text-white flex-shrink-0"
                      aria-hidden="true"
                    >
                      {tile.shape}
                    </span>

                    <span className="flex-1 text-white font-semibold text-lg leading-snug break-words">
                      {option}
                    </span>

                    {isSelected && !isRevealing && (
                      <span className="flex-shrink-0 rounded-full bg-white/95 px-3 py-1 text-xs font-black uppercase text-gray-900">
                        Locked
                      </span>
                    )}

                    {isCorrect && (
                      <span
                        className="flex-shrink-0 text-2xl"
                        aria-hidden="true"
                      >
                        âœ…
                      </span>
                    )}

                    {isSelected && isRevealing && !isCorrect && (
                      <span
                        className="flex-shrink-0 text-2xl"
                        aria-hidden="true"
                      >
                        âŒ
                      </span>
                    )}
                  </button>
                );
              })}
            </div>

            {!isAnswering && !isRevealing && !isLeaderboard && (
              <p className="text-center text-sm text-gray-400">
                {expired
                  ? "â± Time's up â€” waiting for the hostâ€¦"
                  : "Answer locked â€” waiting for the host to continueâ€¦"}
              </p>
            )}
          </div>
        )}

              {/* My Result */}
              {myResult && (isRevealing || isLeaderboard) && (
                <div className={cn(
                  "mt-6 p-4 rounded-xl text-center",
                  myResult.isCorrect ? "bg-green-900/30 border border-green-500" : "bg-red-900/30 border border-red-500"
                )}>
                  <p className="text-lg font-bold">
                    {myResult.isCorrect ? "âœ… Correct!" : "âŒ Incorrect"}
                  </p>
                  {reveal?.explanation && (
                    <p className="text-sm text-gray-300 mt-2 italic">ðŸ’¡ {reveal.explanation}</p>
                  )}
                </div>
              )}

        {/* Leaderboard */}
        {/* Players never see scores: the host announces results. */}
        {isLeaderboard && (
          <Card variant="outlined" className="text-center py-8">
            <CardContent>
              <p className="text-gray-300 font-medium">Round complete â€” waiting for the hostâ€¦</p>
            </CardContent>
          </Card>
        )}
        {/* Waiting for next question */}
        {game && game.state === GameState.QUESTION_REVEAL && !reveal && (
          <Card variant="outlined" className="text-center py-12">
            <CardContent>
              <div className="animate-spin rounded-full h-12 w-12 border-4 border-purple-600 border-t-transparent mx-auto mb-4" />
              <p className="text-gray-400">Waiting for next question...</p>
            </CardContent>
          </Card>
        )}

        {/* Error banner */}
        {error && (
          <div className="fixed bottom-4 right-4 z-50 max-w-sm animate-in slide-in-from-right">
            <div className="bg-red-900/90 border border-red-700 rounded-lg p-4 shadow-lg">
              <p className="text-red-300 text-sm">{error}</p>
            </div>
          </div>
        )}

        {/* Reconnect overlay */}
        {showReconnect && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm">
            <Card className="w-full max-w-md text-center">
              <CardContent className="py-8">
                <div className="text-5xl mb-4">ðŸ“¡</div>
                <h2 className="text-xl font-bold mb-2">Connection Lost</h2>
                <p className="text-gray-400 mb-6">Trying to reconnect...</p>
                <Button onClick={handleRejoin} variant="outline">Reconnect Now</Button>
                <Button variant="ghost" onClick={handleLeave} className="mt-3 w-full">Leave Game</Button>
              </CardContent>
            </Card>
          </div>
        )}
      </main>
    </div>
  );
}
