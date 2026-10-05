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
import { Player, Team } from "../types/game";

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

  // Keep callback stable so the WebSocket hook does not
  // reconnect unnecessarily during React re-renders.
  const handleSocketError = useCallback((err: any) => {
    setError(err?.message || "WebSocket error");
  }, []);

  const {
    connected,
    game: wsGame,
    players,
    teams,
    startGame,
    cancelGame,
  } = useGameSocket({
    gamePin: game?.game_pin || "",
    hostToken: hostToken || undefined,
    onError: handleSocketError,
  });

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

  const displayPlayers =
    players.length > 0
      ? players
      : lobby?.players || [];

  const displayTeams =
    teams.length > 0
      ? teams
      : lobby?.teams || [];

  const gameState =
    (displayGame as any).state ||
    game.status ||
    "LOBBY";

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
          MAIN GRID
      ====================================================== */}

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

                    <span className="text-lg font-bold text-purple-400">
                      {player.score}
                    </span>

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
            <h2 className="text-xl font-semibold">
              Game Info
            </h2>
          </CardHeader>

          <CardContent className="space-y-4">

            <div className="p-4 bg-gray-800/50 rounded-lg text-center">

              <p className="text-gray-500 text-sm">
                Game PIN
              </p>

              <p className="font-mono text-3xl font-bold text-purple-400 tracking-widest mt-1">
                {game.game_pin}
              </p>

            </div>

            <div className="space-y-2 text-sm">

              <div className="flex justify-between">
                <span className="text-gray-500">
                  Status
                </span>

                <span className="font-medium capitalize">
                  {gameState
                    .toLowerCase()
                    .replaceAll("_", " ")}
                </span>
              </div>

              <div className="flex justify-between">
                <span className="text-gray-500">
                  Mode
                </span>

                <span className="font-medium">
                  {game.mode === "team"
                    ? "Team (max 4/team)"
                    : "Individual"}
                </span>
              </div>

              <div className="flex justify-between">
                <span className="text-gray-500">
                  Quiz
                </span>

                <span className="font-medium truncate max-w-[150px]">
                  {game.quiz_title}
                </span>
              </div>

              <div className="flex justify-between">
                <span className="text-gray-500">
                  Questions
                </span>

                <span className="font-medium">
                  {game.question_count}
                </span>
              </div>

              <div className="flex justify-between">
                <span className="text-gray-500">
                  Players
                </span>

                <span className="font-medium">
                  {displayPlayers.length}
                </span>
              </div>

              <div className="flex justify-between">
                <span className="text-gray-500">
                  Teams
                </span>

                <span className="font-medium">
                  {displayTeams.length}
                </span>
              </div>

            </div>

            <div className="pt-4 border-t border-gray-700">

              <p className="text-xs text-gray-500 text-center">
                Share the PIN above with players.
                They join at /join
              </p>

            </div>

            {/* Share Link */}

            <div className="pt-4 border-t border-gray-700">

              <p className="text-xs text-gray-500 text-center mb-2">
                Or share a direct link:
              </p>

              <div className="flex gap-2">

                <input
                  type="text"
                  readOnly
                  value={`${window.location.origin}/join?pin=${game.game_pin}`}
                  className="flex-1 px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                />

                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    const link =
                      `${window.location.origin}/join?pin=${game.game_pin}`;

                    navigator.clipboard
                      .writeText(link)
                      .then(() => {
                        alert(
                          "Link copied to clipboard!"
                        );
                      })
                      .catch(() => {
                        setError(
                          "Could not copy link to clipboard."
                        );
                      });
                  }}
                >
                  Copy Link
                </Button>

              </div>

            </div>

          </CardContent>

        </Card>

      </div>
    </div>
  );
}