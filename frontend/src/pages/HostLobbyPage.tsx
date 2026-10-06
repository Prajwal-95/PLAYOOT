import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  api,
  GameLookupOut,
  LobbyOut,
  TeamOut,
  PlayerOut,
  GameCreateIn,
} from "../services/api";
import { useGameSocket } from "../hooks/useGameSocket";
import { Button } from "../components/ui/Button";
import {
  Card,
  CardHeader,
  CardContent,
} from "../components/ui/Card";
import { cn } from "../utils/cn";
import { Player, Team, GameState } from "../types/game";
import { HostGamePanel } from "../components/game/HostGamePanel";
import {
  Copy,
  Share2,
  AlertCircle,
  Check,
  X,
  UserX,
} from "lucide-react";

export function HostLobbyPage() {
  const { quizId, gamePin } = useParams<{
    quizId?: string;
    gamePin?: string;
  }>();

  const navigate = useNavigate();

  const [game, setGame] = useState<GameLookupOut | null>(null);
  const [lobby, setLobby] = useState<LobbyOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [creatingGame, setCreatingGame] = useState(false);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);

  // Host authentication token
  const hostToken = localStorage.getItem("access_token");

  // Share link state
  const [shareLink, setShareLink] = useState<string>("");
  const [copyFeedback, setCopyFeedback] = useState<"idle" | "success" | "error">("idle");
  const [removeConfirm, setRemoveConfirm] = useState<{ playerId: number; nickname: string } | null>(null);

  // Keep callback stable so the WebSocket hook does not
  // reconnect unnecessarily during React re-renders.
  const handleSocketError = useCallback((err: any) => {
    setError(err?.message || "WebSocket error");
  }, []);

  // Stabilise the PIN given to the socket: `game?.game_pin` flips from ""
  // to the real PIN once the REST load finishes.  Passing the flipping value
  // straight into useGameSocket recreates connect()/disconnect() mid-flight,
  // which closed the host socket exactly when QUESTION_STARTED arrived (the
  // host never saw the question or its timer).  Latch the first non-empty
  // PIN and never change it afterwards.
  const [socketPin, setSocketPin] = useState("");

  useEffect(() => {
    const pin = game?.game_pin;
    if (pin && !socketPin) {
      setSocketPin(pin);
    }
  }, [game?.game_pin, socketPin]);

  // Generate share link when game PIN is available
  useEffect(() => {
    if (game?.game_pin) {
      setShareLink(`${window.location.origin}/join?pin=${game.game_pin}`);
    }
  }, [game?.game_pin]);

  const {
    connected,
    role,
    game: wsGame,
    players,
    teams,
    currentQuestion,
    reveal,
    leaderboard,
    timeRemainingMs,
    hasMoreQuestions,
    winnersCount,
    startGame,
    nextQuestion,
    endQuestion,
    endGame,
    cancelGame,
  } = useGameSocket({
    gamePin: socketPin,
    hostToken: hostToken || undefined,
    onError: handleSocketError,
  });

  // Remove player handler
  const handleRemovePlayer = useCallback(async (playerId: number, nickname: string) => {
    setRemoveConfirm({ playerId, nickname });
  }, []);

  const confirmRemovePlayer = useCallback(async () => {
    if (!removeConfirm || !game) return;

    try {
      setError("");
      await api.removePlayer(game.game_pin, removeConfirm.playerId);
      // The WebSocket will receive PLAYER_LEFT and update the roster
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove player");
    } finally {
      setRemoveConfirm(null);
    }
  }, [removeConfirm, game]);

  const cancelRemovePlayer = useCallback(() => {
    setRemoveConfirm(null);
  }, []);

  // Copy share link to clipboard.
  //
  // The payload is ONLY the public join URL - never a token, never a JWT, never
  // a game secret.  `navigator.clipboard` is unavailable on insecure origins,
  // so a hidden-textarea execCommand fallback keeps the button working there
  // too, and the confirmation is rendered inline (no browser alert()).
  const handleCopyLink = useCallback(async () => {
    if (!shareLink) return;

    const fallbackCopy = (): boolean => {
      try {
        const input = document.createElement("textarea");
        input.value = shareLink;
        input.setAttribute("readonly", "");
        input.style.position = "fixed";
        input.style.top = "-1000px";
        input.style.opacity = "0";
        document.body.appendChild(input);
        input.select();
        input.setSelectionRange(0, shareLink.length);
        const ok = document.execCommand("copy");
        document.body.removeChild(input);
        return ok;
      } catch {
        return false;
      }
    };

    let copied = false;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(shareLink);
        copied = true;
      }
    } catch {
      copied = false;
    }

    if (!copied) {
      copied = fallbackCopy();
    }

    setCopyFeedback(copied ? "success" : "error");
    window.setTimeout(() => setCopyFeedback("idle"), 3000);
  }, [shareLink]);

  // Native share
  const handleNativeShare = useCallback(async () => {
    if (!shareLink || !game) return;

    if (navigator.share) {
      try {
        await navigator.share({
          title: "PLAYOOT Quiz",
          text: `Join the game: ${game.quiz_title}`,
          url: shareLink,
        });
      } catch (err) {
        // User cancelled or share failed - fallback to copy
        if (err instanceof Error && err.name !== "AbortError") {
          handleCopyLink();
        }
      }
    } else {
      handleCopyLink();
    }
  }, [shareLink, game, handleCopyLink]);

  // ---------------------------------------------------------
  // CREATE GAME FROM QUIZ
  // Route: /host/quiz/:quizId
  // ---------------------------------------------------------

  const createGameFromQuiz = useCallback(async () => {
    if (!quizId) {
      return;
    }

    const parsedQuizId = Number.parseInt(quizId, 10);

    if (!Number.isFinite(parsedQuizId)) {
      setError("Invalid quiz ID.");
      setLoading(false);
      return;
    }

    setCreatingGame(true);
    setLoading(true);
    setError("");

    try {
      const payload: GameCreateIn = {
        quiz_id: parsedQuizId,
        mode: "individual",
      };

      const newGame = await api.createGame(payload);

      setGame(newGame);

      // The newly-created game is identified by its GAME PIN.
      // From this point onward /host/:gamePin loads the game.
      navigate(`/host/${newGame.game_pin}`, {
        replace: true,
      });
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to create game"
      );
      setLoading(false);
    } finally {
      setCreatingGame(false);
    }
  }, [quizId, navigate]);

  // ---------------------------------------------------------
  // LOAD EXISTING GAME
  // Route: /host/:gamePin
  // ---------------------------------------------------------

  const loadGame = useCallback(async () => {
    if (!gamePin) {
      return;
    }

    setLoading(true);
    setError("");

    try {
      const gameData = await api.lookupGame(gamePin);

      setGame(gameData);

      const lobbyData = await api.getLobby(
        gameData.game_pin
      );

      setLobby(lobbyData);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to load game"
      );
      setGame(null);
    } finally {
      setLoading(false);
    }
  }, [gamePin]);

  // ---------------------------------------------------------
  // ROUTE HANDLER
  // ---------------------------------------------------------

  useEffect(() => {
    if (quizId) {
      createGameFromQuiz();
      return;
    }

    if (gamePin) {
      loadGame();
      return;
    }

    setError("No quiz ID or game PIN was provided.");
    setLoading(false);
  }, [
    quizId,
    gamePin,
    createGameFromQuiz,
    loadGame,
  ]);

  // ---------------------------------------------------------
  // HOST ACTIONS
  // ---------------------------------------------------------

  const handleStartGame = async () => {
    if (!game) {
      return;
    }

    setStarting(true);
    setError("");

    try {
      startGame();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to start game"
      );
    } finally {
      setStarting(false);
    }
  };

  const handleCancelGame = () => {
    const confirmed = confirm(
      "Cancel this game? All players will be disconnected."
    );

    if (!confirmed) {
      return;
    }

    cancelGame();
    navigate("/dashboard");
  };

  // ---------------------------------------------------------
  // LOADING
  // ---------------------------------------------------------

  if (loading || creatingGame) {
    return (
      <div className="max-w-4xl mx-auto">
        <div className="animate-pulse space-y-6">
          <div className="h-8 bg-gray-800 rounded w-1/4" />

          <Card variant="outlined">
            <CardContent className="py-12">
              <div className="h-6 bg-gray-700 rounded w-3/4" />
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------
  // GAME NOT FOUND / ERROR
  // ---------------------------------------------------------

  if (!game) {
    return (
      <div className="max-w-4xl mx-auto text-center py-16">
        <h2 className="text-xl font-semibold">
          Game not found
        </h2>

        {error && (
          <p className="text-red-400 text-sm mt-3">
            {error}
          </p>
        )}

        <Button
          variant="outline"
          onClick={() => navigate("/dashboard")}
          className="mt-4"
        >
          Back to Dashboard
        </Button>
      </div>
    );
  }

  // ---------------------------------------------------------
  // LIVE DATA
  // ---------------------------------------------------------

  // WebSocket data is preferred because it is live.
  // REST data is used as the fallback.
  const displayGame = wsGame || game;

  // WebSocket data is authoritative because it is live.  The REST lobby is
  // only a bootstrap fallback: once the socket has delivered a roster we must
  // trust it, otherwise a stale `lobby` snapshot silently masks live updates.
  // The socket roster is only "live" while the socket is actually connected;
  // a stale post-disconnect snapshot of `[]` must never blank the list.
  const hasLiveRoster =
    connected && (players.length > 0 || teams.length > 0);

  const displayPlayers = hasLiveRoster
    ? players
    : lobby?.players || [];

  const displayTeams = hasLiveRoster ? teams : lobby?.teams || [];

  console.log("[HOST LOBBY] roster render", {
    gamePin: game?.game_pin,
    players: displayPlayers.length,
    live: hasLiveRoster,
  });

  const gameState =
    (displayGame as any).state ||
    game.status ||
    "LOBBY";

  // The lobby grid is only meaningful before the quiz opens.  Once the backend
  // starts the quiz we swap in the live host stage, which is fed entirely by
  // QUESTION_STARTED / QUESTION_ENDED / LEADERBOARD_UPDATED.
  const isPlaying =
    role !== "player" &&
    (gameState === GameState.QUESTION_ACTIVE ||
      gameState === GameState.QUESTION_REVEAL ||
      gameState === GameState.LEADERBOARD ||
      gameState === GameState.FINISHED);

  // ---------------------------------------------------------
  // PLAYER HELPERS
  // ---------------------------------------------------------

  const getPlayerId = (
    player: PlayerOut | Player
  ) =>
    (player as any).player_id ??
    (player as any).playerId ??
    player.nickname;

  const getPlayerTeamName = (
    player: PlayerOut | Player
  ) =>
    (player as any).team_name ??
    (player as any).teamName;

  // ---------------------------------------------------------
  // TEAM HELPERS
  // ---------------------------------------------------------

  const getTeamId = (
    team: TeamOut | Team
  ) =>
    (team as any).team_id ??
    (team as any).teamId;

  const getTeamName = (
    team: TeamOut | Team
  ) =>
    (team as any).name;

  const getTeamMemberCount = (
    team: TeamOut | Team
  ) =>
    (team as any).member_count ??
    (team as any).memberCount ??
    0;

  const getTeamMaxSize = (
    team: TeamOut | Team
  ) =>
    (team as any).max_size ??
    (team as any).maxSize ??
    4;

  const getTeamIsFull = (
    team: TeamOut | Team
  ) =>
    (team as any).is_full ??
    (team as any).isFull ??
    false;

  const getTeamMembers = (
    team: TeamOut | Team
  ) =>
    (team as any).members ?? [];

  // ---------------------------------------------------------
  // UI
  // ---------------------------------------------------------

  return (
    <div className="max-w-4xl mx-auto space-y-6">

      {/* =====================================================
          HEADER
      ====================================================== */}

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">

        <div>
          <div className="flex flex-wrap items-center gap-2 sm:gap-3 mb-2">

            <h1 className="text-2xl sm:text-3xl font-bold break-words min-w-0">
              {game.quiz_title}
            </h1>

            <span
              className={cn(
                "px-3 py-1 text-xs sm:text-sm font-medium rounded-full whitespace-nowrap flex-shrink-0",

                gameState === "LOBBY" &&
                  "bg-gray-700 text-gray-300",

                gameState === "QUESTION_ACTIVE" &&
                  "bg-yellow-900/30 text-yellow-400",

                gameState === "LEADERBOARD" &&
                  "bg-blue-900/30 text-blue-400",

                gameState === "FINISHED" &&
                  "bg-green-900/30 text-green-400",

                gameState === "CANCELLED" &&
                  "bg-red-900/30 text-red-400"
              )}
            >
              {gameState}
            </span>

            {connected && (
              <span className="text-green-400 text-sm flex items-center gap-1">
                Live
              </span>
            )}

          </div>

          <p className="text-sm sm:text-base text-gray-400 break-words">

            Game PIN:{" "}

            <span className="font-mono text-xl sm:text-2xl font-bold text-purple-400 tracking-widest">
              {game.game_pin}
            </span>

            {" | Mode: "}

            {game.mode === "team"
              ? "Team"
              : "Individual"}

            {" | Questions: "}

            {game.question_count}

          </p>
        </div>

        <div className="flex flex-wrap gap-3">

          <Button
            variant="outline"
            onClick={() => navigate("/dashboard")}
          >
            Dashboard
          </Button>

          {gameState === "LOBBY" &&
            displayPlayers.length > 0 && (
              <Button
                onClick={handleStartGame}
                loading={starting}
                size="lg"
              >
                {starting
                  ? "Starting..."
                  : "Start Game"}
              </Button>
            )}

          {gameState !== "LOBBY" &&
            gameState !== "FINISHED" &&
            gameState !== "CANCELLED" && (
              <Button
                variant="outline"
                onClick={handleCancelGame}
              >
                Cancel Game
              </Button>
            )}

        </div>
      </div>

      {/* =====================================================
          ERROR
      ====================================================== */}

      {error && (
        <div
          className="text-sm text-red-400 p-4 bg-red-900/20 border border-red-900/50 rounded-lg"
          role="alert"
        >
          {error}
        </div>
      )}

      {/* =====================================================
          LIVE HOST STAGE
      ====================================================== */}

      {isPlaying &&
        (currentQuestion || reveal ? (
          <HostGamePanel
            gameState={gameState as GameState}
            currentQuestion={currentQuestion}
            reveal={reveal}
            leaderboard={leaderboard}
            timeRemainingMs={timeRemainingMs}
            playerCount={displayPlayers.length}
            hasMoreQuestions={hasMoreQuestions}
            onNextQuestion={nextQuestion}
            onEndQuestion={endQuestion}
            onEndGame={endGame}
            totalQuestions={game.question_count}
            winnersCount={winnersCount ?? 3}
            // The app-shell nav above this page is h-16, so the sticky bar
            // docks directly underneath it.
            stickyOffset="top-16"
          />
        ) : (
          <Card variant="outlined">
            <CardContent className="py-16 text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-4 border-purple-600 border-t-transparent mx-auto" />
              <p className="text-gray-400 mt-4">
                Waiting for the first question…
              </p>
            </CardContent>
          </Card>
        ))}

      {/* =====================================================
          SHARE / JOIN  (prominent)
          Carries ONLY the public join URL - never a token or JWT.
      ====================================================== */}

      {!isPlaying && (
        <Card
          variant="outlined"
          className="border-purple-500/40 bg-gradient-to-br from-purple-900/25 via-gray-900 to-indigo-900/25 overflow-hidden"
        >
          <CardContent className="p-5 sm:p-7">
            <div className="flex flex-col lg:flex-row gap-6 lg:items-center">
              {/* GAME PIN */}
              <div className="lg:flex-shrink-0 p-5 rounded-2xl bg-black/40 border border-purple-500/40 text-center">
                <p className="text-[11px] uppercase tracking-[0.3em] text-gray-400 mb-2">
                  Game PIN
                </p>
                <p className="font-mono text-5xl sm:text-6xl font-black text-purple-300 tracking-[0.15em]">
                  {game.game_pin}
                </p>
              </div>

              {/* SHARE LINK */}
              <div className="flex-1 min-w-0 space-y-3">
                <p className="text-[11px] uppercase tracking-[0.3em] text-gray-400">
                  Share link
                </p>

                <div className="flex flex-col sm:flex-row gap-2">
                  <input
                    type="text"
                    readOnly
                    value={
                      shareLink ||
                      `${window.location.origin}/join?pin=${game.game_pin}`
                    }
                    onFocus={(event) => event.currentTarget.select()}
                    className="flex-1 min-w-0 bg-black/40 border border-gray-700 rounded-xl px-4 py-3 text-white text-sm font-mono focus:outline-none focus:ring-2 focus:ring-purple-500"
                    aria-label="Game join link"
                  />

                  <Button
                    variant="outline"
                    size="lg"
                    onClick={handleCopyLink}
                    className="whitespace-nowrap"
                    aria-label={
                      copyFeedback === "success" ? "Link copied!" : "Copy link"
                    }
                  >
                    {copyFeedback === "success" ? (
                      <>
                        <Check className="w-4 h-4 mr-2 text-green-400" />
                        Link copied!
                      </>
                    ) : (
                      <>
                        <Copy className="w-4 h-4 mr-2" />
                        Copy Link
                      </>
                    )}
                  </Button>

                  <Button
                    variant="outline"
                    size="lg"
                    onClick={handleNativeShare}
                    className="whitespace-nowrap"
                  >
                    <Share2 className="w-4 h-4 mr-2" />
                    Share
                  </Button>
                </div>

                {copyFeedback === "success" && (
                  <p
                    className="text-sm text-green-400 flex items-center gap-2"
                    role="status"
                  >
                    <Check className="w-4 h-4 flex-shrink-0" />
                    Link copied!
                  </p>
                )}

                {copyFeedback === "error" && (
                  <p className="text-sm text-red-400" role="alert">
                    Could not copy automatically — select the link and copy it
                    manually.
                  </p>
                )}

                <p className="text-xs text-gray-500">
                  Players open this link → enter a nickname → join instantly.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* =====================================================
          MAIN GRID
      ====================================================== */}

      {!isPlaying && (
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* ===================================================
            PLAYERS
        ==================================================== */}

        <Card
          variant="outlined"
          className="lg:col-span-2"
        >
          <CardHeader className="flex items-center justify-between">

            <h2 className="text-xl font-semibold">
              Players ({displayPlayers.length})
            </h2>

            {game.mode === "team" &&
              displayTeams.length < 10 && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    navigate(
                      `/host/${game.game_id}/teams`
                    )
                  }
                >
                  Manage Teams
                </Button>
              )}

          </CardHeader>

          <CardContent>

            {displayPlayers.length === 0 ? (

              <div className="text-center py-12 text-gray-500">

                <p className="text-2xl mb-2">
                  Players
                </p>

                <p>
                  No players joined yet
                </p>

                <p className="text-sm">
                  Share the PIN:{" "}
                  <span className="font-mono text-lg">
                    {game.game_pin}
                  </span>
                </p>

              </div>

            ) : (

              <div className="space-y-2">

                {displayPlayers.map((player) => (

                  <div
                    key={getPlayerId(player)}
                    className="flex items-center justify-between p-3 bg-gray-800/50 rounded-lg"
                  >

                    <div className="flex items-center gap-3">

                      <span className="w-8 h-8 rounded-full bg-purple-600 flex items-center justify-center text-sm font-bold">
                        {player.nickname
                          .charAt(0)
                          .toUpperCase()}
                      </span>

                      <div>

                        <p className="font-medium">
                          {player.nickname}
                        </p>

                        <p className="text-sm text-gray-500">

                          {getPlayerTeamName(
                            player
                          )
                            ? `Team: ${getPlayerTeamName(
                                player
                              )}`
                            : "No team"}

                          {" | "}

                          {player.connected ? (
                            <span className="text-green-400">
                              Connected
                            </span>
                          ) : (
                            <span className="text-yellow-400">
                              Disconnected
                            </span>
                          )}

                        </p>

                      </div>

                    </div>

                    <div className="flex items-center gap-3">
                      <span className="text-lg font-bold text-purple-400">
                        {player.score}
                      </span>
                      {/* Remove player button - only for disconnected players or in LOBBY */}
                      {(gameState === "LOBBY" || !player.connected) && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-red-400 hover:bg-red-900/20 p-1.5"
                          onClick={() => handleRemovePlayer(getPlayerId(player), player.nickname)}
                          aria-label={`Remove ${player.nickname}`}
                          title="Remove player"
                        >
                          <UserX className="w-4 h-4" />
                        </Button>
                      )}
                    </div>

                  </div>

                ))}

              </div>

            )}

          </CardContent>
        </Card>

        {/* ===================================================
            TEAMS
        ==================================================== */}

        {game.mode === "team" && (

          <Card variant="outlined">

            <CardHeader>
              <h2 className="text-xl font-semibold">
                Teams ({displayTeams.length})
              </h2>
            </CardHeader>

            <CardContent>

              {displayTeams.length === 0 ? (

                <div className="text-center py-8 text-gray-500">

                  <p>
                    No teams created yet
                  </p>

                  <p className="text-sm">
                    Players can create teams after joining
                  </p>

                </div>

              ) : (

                <div className="space-y-3">

                  {displayTeams.map((team) => (

                    <div
                      key={getTeamId(team)}
                      className="p-3 bg-gray-800/50 rounded-lg"
                    >

                      <div className="flex items-center justify-between mb-2">

                        <h4 className="font-semibold">
                          {getTeamName(team)}
                        </h4>

                        <span className="text-sm text-gray-500">

                          {getTeamMemberCount(
                            team
                          )}

                          /

                          {getTeamMaxSize(
                            team
                          )}

                          {getTeamIsFull(team) && (
                            <span className="text-red-400 ml-1">
                              (Full)
                            </span>
                          )}

                        </span>

                      </div>

                      <div className="flex flex-wrap gap-1">

                        {getTeamMembers(team).map(
                          (
                            member: PlayerOut | Player
                          ) => (

                            <span
                              key={getPlayerId(member)}
                              className="px-2 py-1 text-xs bg-gray-700 rounded"
                            >
                              {member.nickname}
                            </span>

                          )
                        )}

                      </div>

                    </div>

                  ))}

                </div>

              )}

            </CardContent>

          </Card>

        )}

        {/* ===================================================
            GAME INFO
        ==================================================== */}

        <Card variant="outlined">

          <CardHeader>
            <h2 className="text-xl font-semibold flex items-center gap-2">
              <span className="text-purple-400">🎮</span>
              Game Info
            </h2>
          </CardHeader>

          <CardContent className="space-y-4">

            {/* Game Details */}
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">Status</span>
                <span className="font-medium capitalize text-white">
                  {gameState.toLowerCase().replaceAll("_", " ")}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Mode</span>
                <span className="font-medium text-white">
                  {game.mode === "team" ? "Team (max 4/team)" : "Individual"}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Quiz</span>
                <span className="font-medium text-white truncate max-w-[150px]">
                  {game.quiz_title}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Questions</span>
                <span className="font-medium text-white">{game.question_count}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Players</span>
                <span className="font-medium text-white">{displayPlayers.length}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Teams</span>
                <span className="font-medium text-white">{displayTeams.length}</span>
              </div>
            </div>

          </CardContent>

        </Card>

      </div>
      )}

      {/* Remove Player Confirmation Modal */}
      {removeConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
          <Card className="w-full max-w-md">
            <CardContent className="p-6 space-y-4">
              <div className="text-center">
                <div className="w-12 h-12 rounded-full bg-red-900/30 border border-red-500/30 flex items-center justify-center mx-auto mb-3">
                  <AlertCircle className="w-6 h-6 text-red-400" />
                </div>
                <h3 className="text-lg font-semibold">Remove Player</h3>
                <p className="text-gray-400 mt-1">
                  Remove <strong className="text-white">{removeConfirm.nickname}</strong> from this game?
                </p>
                <p className="text-xs text-gray-500 mt-2">
                  Their seat will be freed and they can rejoin with a new nickname.
                </p>
              </div>
              <div className="flex gap-3">
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={cancelRemovePlayer}
                >
                  Cancel
                </Button>
                <Button
                  variant="danger"
                  className="flex-1"
                  onClick={confirmRemovePlayer}
                >
                  Remove
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

    </div>
  );
}