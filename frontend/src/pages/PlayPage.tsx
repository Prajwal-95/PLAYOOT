import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useGameSocket } from "../hooks/useGameSocket";
import { GameState } from "../types/game";
import { Button } from "../components/ui/Button";
import { Card, CardHeader, CardContent, CardFooter } from "../components/ui/Card";
import { cn } from "../utils/cn";
import { formatDistanceToNow } from "date-fns";

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
    timeRemainingMs,
    alreadyAnswered,
    myResult,
    me,
    leaderboard,
    submitAnswer,
    requestState,
    disconnect,
    reconnect,
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
            <div className="text-6xl mb-4">🎮</div>
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
                <p className="text-sm text-gray-500 mt-2">Score: {me.score}</p>
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

  // Game cancelled/finished
  if (game && (game.state === GameState.CANCELLED || game.state === GameState.FINISHED)) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <Card className="w-full max-w-md text-center">
          <CardContent className="py-12">
            <div className="text-6xl mb-4">
              {game.state === GameState.FINISHED ? "🏆" : "🚫"}
            </div>
            <h1 className="text-2xl font-bold mb-2">
              {game.state === GameState.FINISHED ? "Game Finished!" : "Game Cancelled"}
            </h1>
            <p className="text-gray-400 mb-6">
              {game.state === GameState.FINISHED 
                ? "Thanks for playing!" 
                : "The host cancelled the game."}
            </p>
            {leaderboard && leaderboard.entries.length > 0 && (
              <div className="mb-6 text-left max-h-64 overflow-auto">
                <h3 className="font-semibold mb-3">Final Leaderboard</h3>
                {leaderboard.entries.slice(0, 10).map((entry) => (
                  <div key={entry.id} className="py-2 border-b border-gray-800">
                    <div className="flex items-center gap-3 mb-1">
                      <span className={cn(
                        "w-6 h-6 rounded-full flex items-center justify-center font-bold text-xs flex-shrink-0",
                        entry.rank === 1 ? "bg-yellow-500 text-black" :
                        entry.rank === 2 ? "bg-gray-400 text-black" :
                        entry.rank === 3 ? "bg-amber-700 text-white" :
                        "bg-gray-700 text-gray-300"
                      )}>
                        #{entry.rank}
                      </span>
                      <p className={cn(
                        "font-medium truncate",
                        entry.playerId === me?.playerId && "text-purple-400"
                      )}>
                        {entry.name}
                      </p>
                    </div>
                    <div className="flex items-center justify-between text-sm text-gray-400">
                      <span className="font-bold text-purple-400">{entry.score} pts</span>
                      {leaderboard.mode === "team" && entry.avgResponseTimeMs !== undefined && (
                        <span className="flex items-center gap-2 text-xs">
                          <span className="flex items-center gap-1 text-green-400">
                            <span>✓</span>{entry.correctAnswers}
                          </span>
                          <span className="flex items-center gap-1 text-red-400">
                            <span>✗</span>{entry.incorrectAnswers}
                          </span>
                          <span className="flex items-center gap-1">
                            ⏱{Math.round(entry.avgResponseTimeMs / 1000)}s
                          </span>
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
            
            {/* Winners Announcement */}
            {game.state === GameState.FINISHED && leaderboard && leaderboard.entries.length > 0 && (
              <div className="mb-6 p-4 bg-gradient-to-r from-yellow-500/20 to-amber-500/20 border border-yellow-500/30 rounded-xl">
                <h3 className="font-semibold text-yellow-400 mb-3 flex items-center gap-2">
                  <span className="text-2xl">🏆</span>
                  Winners
                </h3>
                <div className="flex flex-wrap gap-2 justify-center">
                  {leaderboard.entries.slice(0, 3).map((entry) => (
                    <div key={entry.id} className="flex items-center gap-2 px-3 py-2 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
                      <span className={cn(
                        "w-6 h-6 rounded-full flex items-center justify-center font-bold text-xs flex-shrink-0",
                        entry.rank === 1 ? "bg-yellow-500 text-black" :
                        entry.rank === 2 ? "bg-gray-400 text-black" :
                        entry.rank === 3 ? "bg-amber-700 text-white" :
                        "bg-gray-700 text-gray-300"
                      )}>
                        #{entry.rank}
                      </span>
                      <span className="font-medium text-yellow-300">{entry.name}</span>
                      <span className="text-xs text-yellow-500">{entry.score} pts</span>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-yellow-400/80 mt-2 text-center">
                  Congratulations to the winners! 🎉
                </p>
              </div>
            )}
            
            <Button variant="outline" onClick={handleLeave} className="w-full">
              Return to Join
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Question active or reveal/leaderboard
  const displayQuestion = currentQuestion || reveal;
  const isAnswering = game?.state === GameState.QUESTION_ACTIVE && displayQuestion && !alreadyAnswered;
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
              <span className="text-xl flex-shrink-0">🎮</span>
              <h1 className="font-bold text-base sm:text-lg truncate">{game?.quizTitle || "PLAYOOT"}</h1>
              <span className="px-2 py-0.5 text-xs font-medium rounded bg-gray-800 text-gray-400 flex-shrink-0 whitespace-nowrap">
                PIN: {gamePin}
              </span>
            </div>
            <div className="flex items-center gap-3">
              {me && (
                <div className="text-right hidden sm:block">
                  <p className="text-xs text-gray-500">{me.nickname}</p>
                  <p className="font-bold text-purple-400">{me.score} pts</p>
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
                {timeRemainingMs !== null ? `${Math.ceil(timeRemainingMs / 1000)}s` : "—"}
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

        {/* Question */}
        {displayQuestion && (
          <Card variant="outlined" className={cn(
            "mb-6",
            isRevealing && "ring-2 ring-yellow-500",
            isLeaderboard && "ring-2 ring-blue-500"
          )}>
            <CardContent className="py-6">
              <div className="mb-4">
                <p className="text-sm text-gray-500 mb-1">
                  Question {displayQuestion.questionNumber} of {displayQuestion.totalQuestions}
                </p>
                <h2 className="text-xl md:text-2xl font-semibold leading-tight">
                  {displayQuestion.question}
                </h2>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {displayQuestion.options.map((option, index) => {
                  const isCorrect = reveal && index === reveal.correctIndex;
                  const isSelected = myResult?.selectedAnswer === index;
                  const wasAnswered = alreadyAnswered || isRevealing || isLeaderboard;

                  let buttonClass = "w-full p-4 rounded-xl text-left font-medium transition-all";
                  
                  if (isAnswering) {
                    buttonClass += " bg-gray-800 border-2 border-gray-600 hover:border-purple-500 hover:bg-gray-700";
                  } else if (wasAnswered) {
                    if (isCorrect) {
                      buttonClass += " bg-green-900/30 border-2 border-green-500";
                    } else if (isSelected) {
                      buttonClass += " bg-red-900/30 border-2 border-red-500";
                    } else {
                      buttonClass += " bg-gray-800 border-2 border-gray-600 opacity-60";
                    }
                  } else {
                    buttonClass += " bg-gray-800 border-2 border-gray-600 opacity-60 cursor-not-allowed";
                  }

                  return (
                    <button
                      key={index}
                      onClick={() => handleAnswer(index)}
                      disabled={!isAnswering}
                      className={buttonClass}
                    >
                      <div className="flex items-center gap-3">
                        <span className={cn(
                          "w-8 h-8 rounded-full flex items-center justify-center font-bold text-lg flex-shrink-0",
                          isCorrect ? "bg-green-500 text-white" :
                          isSelected && !isCorrect ? "bg-red-500 text-white" :
                          "bg-gray-700 text-gray-300"
                        )}>
                          {String.fromCharCode(65 + index)}
                        </span>
                        <span className="flex-1">{option}</span>
                        {isRevealing && isCorrect && (
                          <span className="text-green-400 font-bold">✓ Correct</span>
                        )}
                        {isRevealing && isSelected && !isCorrect && (
                          <span className="text-red-400 font-bold">✗ Wrong</span>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>

              {/* My Result */}
              {myResult && (isRevealing || isLeaderboard) && (
                <div className={cn(
                  "mt-6 p-4 rounded-xl text-center",
                  myResult.isCorrect ? "bg-green-900/30 border border-green-500" : "bg-red-900/30 border border-red-500"
                )}>
                  <p className="text-lg font-bold">
                    {myResult.isCorrect ? "✅ Correct!" : "❌ Incorrect"}
                  </p>
                  <p className="text-sm text-gray-400 mt-1">
                    {myResult.isCorrect 
                      ? `+${myResult.pointsAwarded} points (${myResult.responseTimeMs}ms)`
                      : "0 points"}
                  </p>
                  {reveal?.explanation && (
                    <p className="text-sm text-gray-300 mt-2 italic">💡 {reveal.explanation}</p>
                  )}
                </div>
              )}

              {/* Answer Distribution */}
              {reveal?.distribution && reveal.distribution.length > 0 && (
                <div className="mt-6">
                  <p className="text-sm text-gray-500 mb-3">Answer Distribution</p>
                  <div className="space-y-2">
                    {reveal.distribution.map((count, index) => (
                      <div key={index} className="flex items-center gap-3">
                        <span className="w-8 h-8 rounded-full bg-gray-700 flex items-center justify-center text-sm font-bold flex-shrink-0">
                          {String.fromCharCode(65 + index)}
                        </span>
                        <div className="flex-1 h-3 bg-gray-800 rounded-full overflow-hidden">
                          <div 
                            className={cn(
                              "h-full rounded-full transition-all duration-500",
                              index === reveal.correctIndex ? "bg-green-500" : "bg-purple-500"
                            )}
                            style={{ width: `${(displayQuestion.playerCount ?? 0) > 0 ? (count / (displayQuestion.playerCount ?? 0)) * 100 : 0}%` }}
                          />
                        </div>
                        <span className="text-sm text-gray-400 w-12 text-right">{count}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Leaderboard */}
        {isLeaderboard && leaderboard && (
          <Card variant="outlined">
            <CardHeader>
              <h2 className="text-xl font-semibold">
                {leaderboard.mode === "team" ? "👥 Team Leaderboard" : "🏆 Leaderboard"}
              </h2>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {leaderboard.entries.slice(0, 10).map((entry) => (
                  <div 
                    key={entry.id} 
                    className={cn(
                      "flex items-center justify-between p-3 rounded-lg",
                      entry.playerId === me?.playerId || entry.teamId === me?.teamId 
                        ? "bg-purple-900/30 ring-1 ring-purple-500" 
                        : "bg-gray-800/50"
                    )}
                  >
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <span className={cn(
                        "w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm flex-shrink-0",
                        entry.rank === 1 ? "bg-yellow-500 text-black" :
                        entry.rank === 2 ? "bg-gray-400 text-black" :
                        entry.rank === 3 ? "bg-amber-700 text-white" :
                        "bg-gray-700 text-gray-300"
                      )}>
                        #{entry.rank}
                      </span>
                      <div className="min-w-0">
                        <p className="font-medium truncate">{entry.name}</p>
                        {leaderboard.mode === "team" && entry.memberCount && (
                          <p className="text-xs text-gray-500">{entry.memberCount} members</p>
                        )}
                        {leaderboard.mode === "team" && entry.avgResponseTimeMs !== undefined && (
                          <div className="flex flex-wrap gap-2 text-xs text-gray-400 mt-1">
                            <span className="flex items-center gap-1">
                              <span>⏱</span>
                              <span>{Math.round(entry.avgResponseTimeMs / 1000)}s avg</span>
                            </span>
                            <span className="flex items-center gap-1 text-green-400">
                              <span>✓</span>
                              <span>{entry.correctAnswers} correct</span>
                            </span>
                            <span className="flex items-center gap-1 text-red-400">
                              <span>✗</span>
                              <span>{entry.incorrectAnswers} wrong</span>
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                    <span className="font-bold text-purple-400 text-lg whitespace-nowrap">{entry.score}</span>
                  </div>
                ))}
              </div>
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
                <div className="text-5xl mb-4">📡</div>
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