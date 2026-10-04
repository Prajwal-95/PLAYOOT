import { useState, useEffect, useCallback, useRef } from "react";
import type {
  GameSnapshot,
  Player,
  Team,
  Question,
  Leaderboard,
  MyResult,
  WSEnvelope,
  ConnectedPayload,
  GameErrorPayload,
  QuestionStartedPayload,
  AnswerSubmittedPayload,
  PlayerAnsweredPayload,
  QuestionEndedPayload,
} from "../types/game";
import {
  WSEventType,
  WSClientAction,
  GameState,
  GameStartedPayload,
  GameFinishedPayload,
  GameCancelledPayload,
} from "../types/game";

interface UseGameSocketOptions {
  gamePin: string;
  playerToken?: string;
  hostToken?: string;
  onError?: (error: GameErrorPayload) => void;
}

interface UseGameSocketReturn {
  // Connection state
  connected: boolean;
  connecting: boolean;
  role: "host" | "player" | null;
  connectionId: string | null;

  // Game state
  game: GameSnapshot["game"] | null;
  players: Player[];
  teams: Team[];
  currentQuestion: Question | null;
  reveal: Question | null;
  leaderboard: Leaderboard | null;
  timeRemainingMs: number | null;
  questionStartedAt: string | null;
  questionEndsAt: string | null;
  alreadyAnswered: boolean;
  myResult: MyResult | null;
  me: Player | null;
  canStart: boolean;
  serverTime: string | null;

  // Actions
  sendAction: (
    action: WSClientAction,
    payload?: Record<string, unknown>
  ) => void;
  submitAnswer: (questionId: string, answerIndex: number) => void;
  requestState: () => void;
  ping: () => void;

  // Host actions
  startGame: () => void;
  nextQuestion: () => void;
  endQuestion: () => void;
  endGame: () => void;
  cancelGame: () => void;

  // Lifecycle
  disconnect: () => void;
  reconnect: () => void;
}

export function useGameSocket({
  gamePin,
  playerToken,
  hostToken,
  onError,
}: UseGameSocketOptions): UseGameSocketReturn {
  // ---------------------------------------------------------
  // WEBSOCKET REFS
  // ---------------------------------------------------------

  const wsRef = useRef<WebSocket | null>(null);

  const reconnectTimeoutRef = useRef<number | null>(null);

  const reconnectAttemptsRef = useRef(0);

  // IMPORTANT:
  // These are refs instead of React state because connect()
  // must not be recreated when connection state changes.
  const connectingRef = useRef(false);

  // Used to distinguish intentional disconnects from
  // unexpected WebSocket closures.
  const intentionalDisconnectRef = useRef(false);

  const maxReconnectAttempts = 5;

  // ---------------------------------------------------------
  // CONNECTION STATE
  // ---------------------------------------------------------

  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [role, setRole] = useState<"host" | "player" | null>(null);
  const [connectionId, setConnectionId] = useState<string | null>(null);

  // ---------------------------------------------------------
  // GAME STATE
  // ---------------------------------------------------------

  const [game, setGame] =
    useState<GameSnapshot["game"] | null>(null);

  const [players, setPlayers] = useState<Player[]>([]);

  const [teams, setTeams] = useState<Team[]>([]);

  const [currentQuestion, setCurrentQuestion] =
    useState<Question | null>(null);

  const [reveal, setReveal] =
    useState<Question | null>(null);

  const [leaderboard, setLeaderboard] =
    useState<Leaderboard | null>(null);

  const [timeRemainingMs, setTimeRemainingMs] =
    useState<number | null>(null);

  const [questionStartedAt, setQuestionStartedAt] =
    useState<string | null>(null);

  const [questionEndsAt, setQuestionEndsAt] =
    useState<string | null>(null);

  const [alreadyAnswered, setAlreadyAnswered] =
    useState(false);

  const [myResult, setMyResult] =
    useState<MyResult | null>(null);

  const [me, setMe] =
    useState<Player | null>(null);

  const [canStart, setCanStart] =
    useState(false);

  const [serverTime, setServerTime] =
    useState<string | null>(null);

  // ---------------------------------------------------------
  // MESSAGE HANDLER
  // ---------------------------------------------------------

  const handleMessage = useCallback(
    (envelope: WSEnvelope) => {
      const { type, payload } = envelope;

      switch (type) {
        // ---------------------------------------------------
        // CONNECTED
        // ---------------------------------------------------

        case WSEventType.CONNECTED: {
          const p = payload as ConnectedPayload;

          console.log("[WS] CONNECTED:", {
            role: p.role,
            gameId: p.gameId,
            gamePin: p.gamePin,
            connectionId: p.connectionId,
          });

          setRole(p.role);
          setConnectionId(p.connectionId);

          setGame({
            gameId: p.gameId,
            gamePin: p.gamePin,
            mode: p.mode,
            state: p.state,
            hostId: 0,
            hostName: "",
            quizId: 0,
            quizTitle: "",
            totalQuestions: 0,
            currentQuestionIndex: 0,
            currentQuestionNumber: 0,
            createdAt: "",
            startedAt: null,
          });

          break;
        }

        // ---------------------------------------------------
        // STATE SYNC
        // ---------------------------------------------------

        case WSEventType.STATE_SYNC: {
          const p = payload as GameSnapshot;

          setGame(p.game);
          setPlayers(p.players);
          setTeams(p.teams);
          setCurrentQuestion(p.currentQuestion);
          setReveal(p.reveal);
          setLeaderboard(p.leaderboard);
          setTimeRemainingMs(p.timeRemainingMs);
          setQuestionStartedAt(p.questionStartedAt);
          setQuestionEndsAt(p.questionEndsAt);
          setAlreadyAnswered(p.alreadyAnswered);
          setMyResult(p.myResult);
          setMe(p.me);
          setCanStart(p.canStart);
          setServerTime(p.serverTime);

          break;
        }

        // ---------------------------------------------------
        // GAME STARTED
        // ---------------------------------------------------

        case WSEventType.GAME_STARTED: {
          const p = payload as GameStartedPayload;

          setGame((prev) =>
            prev
              ? {
                  ...prev,
                  state: GameState.QUESTION_ACTIVE,
                  startedAt: p.startedAt,
                }
              : null
          );

          break;
        }

        // ---------------------------------------------------
        // QUESTION STARTED
        // ---------------------------------------------------

        case WSEventType.QUESTION_STARTED: {
          const p = payload as QuestionStartedPayload;

          setCurrentQuestion({
            questionId: p.questionId,
            questionNumber: p.questionNumber,
            totalQuestions: p.totalQuestions,
            question: p.question,
            options: p.options,
            startedAt: p.startedAt,
            endsAt: p.endsAt,
            timeLimit: p.timeLimit,
            points: p.points,
            timeRemainingMs: p.timeRemainingMs,
            serverTime: p.serverTime,
          });

          setAlreadyAnswered(false);
          setMyResult(null);

          break;
        }

        // ---------------------------------------------------
        // ANSWER SUBMITTED
        // ---------------------------------------------------

        case WSEventType.ANSWER_SUBMITTED: {
          const p = payload as AnswerSubmittedPayload;

          setAlreadyAnswered(true);

          setMyResult({
            selectedAnswer: p.selectedAnswer,
            isCorrect: null,
            responseTimeMs: p.responseTimeMs,
            pointsAwarded: 0,
          });

          break;
        }

        // ---------------------------------------------------
        // PLAYER ANSWERED
        // ---------------------------------------------------

        case WSEventType.PLAYER_ANSWERED: {
          const p = payload as PlayerAnsweredPayload;

          setCurrentQuestion((prev) =>
            prev
              ? {
                  ...prev,
                  answeredCount: p.answeredCount,
                  playerCount: p.playerCount,
                }
              : null
          );

          break;
        }

        // ---------------------------------------------------
        // QUESTION ENDED
        // ---------------------------------------------------

        case WSEventType.QUESTION_ENDED: {
          const p = payload as QuestionEndedPayload;

          setReveal(p.reveal);
          setLeaderboard(p.leaderboard);

          setCurrentQuestion((prev) =>
            prev
              ? {
                  ...prev,
                  ...p.reveal,
                }
              : null
          );

          break;
        }

        // ---------------------------------------------------
        // LEADERBOARD UPDATED
        // ---------------------------------------------------

        case WSEventType.LEADERBOARD_UPDATED: {
          const p = payload as {
            leaderboard: Leaderboard;
            reveal: Question;
            hasMoreQuestions: boolean;
            state: GameState;
          };

          setLeaderboard(p.leaderboard);
          setReveal(p.reveal);

          break;
        }

        // ---------------------------------------------------
        // NEXT QUESTION
        // ---------------------------------------------------

        case WSEventType.NEXT_QUESTION: {
          setCurrentQuestion(null);
          setReveal(null);
          setAlreadyAnswered(false);
          setMyResult(null);

          break;
        }

        // ---------------------------------------------------
        // GAME FINISHED
        // ---------------------------------------------------

        case WSEventType.GAME_FINISHED: {
          const p = payload as GameFinishedPayload;

          setGame((prev) =>
            prev
              ? {
                  ...prev,
                  state: GameState.FINISHED,
                }
              : null
          );

          setLeaderboard(p.finalLeaderboard);

          break;
        }

        // ---------------------------------------------------
        // GAME CANCELLED
        // ---------------------------------------------------

        case WSEventType.GAME_CANCELLED: {
          setGame((prev) =>
            prev
              ? {
                  ...prev,
                  state: GameState.CANCELLED,
                }
              : null
          );

          break;
        }

        // ---------------------------------------------------
        // GAME ERROR
        // ---------------------------------------------------

        case WSEventType.GAME_ERROR: {
          const p = payload as GameErrorPayload;

          console.error("[WS] Game error:", p);

          onError?.(p);

          break;
        }

        // ---------------------------------------------------
        // PLAYER EVENTS
        // ---------------------------------------------------

        case WSEventType.PLAYER_JOINED:
        case WSEventType.PLAYER_LEFT:
        case WSEventType.PLAYER_UPDATED: {
          break;
        }

        // ---------------------------------------------------
        // TEAM EVENTS
        // ---------------------------------------------------

        case WSEventType.TEAM_CREATED:
        case WSEventType.TEAM_JOINED:
        case WSEventType.TEAM_LEFT:
        case WSEventType.TEAM_UPDATED: {
          break;
        }

        // ---------------------------------------------------
        // PONG
        // ---------------------------------------------------

        case WSEventType.PONG: {
          break;
        }

        // ---------------------------------------------------
        // UNKNOWN
        // ---------------------------------------------------

        default: {
          console.log(
            "[WS] Unhandled message type:",
            type
          );
        }
      }
    },
    [onError]
  );

  // ---------------------------------------------------------
  // CONNECT
  // ---------------------------------------------------------

  const connect = useCallback(() => {
    // Already connected.
    if (
      wsRef.current?.readyState === WebSocket.OPEN
    ) {
      console.log("[WS] Already connected");
      return;
    }

    // Connection attempt already running.
    //
    // IMPORTANT:
    // This uses a ref instead of `connecting` state.
    // This prevents connect() from being recreated during
    // the connection process.
    if (connectingRef.current) {
      console.log(
        "[WS] Connection already in progress"
      );
      return;
    }

    // Validate game PIN.
    if (!gamePin) {
      console.error(
        "[WS] Cannot connect: gamePin is empty or undefined",
        {
          gamePin,
        }
      );

      connectingRef.current = false;
      setConnecting(false);

      return;
    }

    // This is a deliberate connection attempt.
    intentionalDisconnectRef.current = false;

    connectingRef.current = true;
    setConnecting(true);

    // -------------------------------------------------------
    // AUTHENTICATION PARAMETERS
    // -------------------------------------------------------

    const params = new URLSearchParams();

    if (playerToken) {
      params.set(
        "player_token",
        playerToken
      );
    }

    if (hostToken) {
      params.set(
        "token",
        hostToken
      );
    }

    // -------------------------------------------------------
    // WEBSOCKET BASE URL
    // -------------------------------------------------------

    const wsBase =
      import.meta.env.VITE_WS_URL ||
      `${
        window.location.protocol === "https:"
          ? "wss:"
          : "ws:"
      }//${window.location.host}`;

    const wsUrl =
      `${wsBase}/ws/game/${gamePin}?${params.toString()}`;

    // -------------------------------------------------------
    // DEBUG LOGGING
    // -------------------------------------------------------

    console.group(
      "[WS] Connection Debug"
    );

    console.log(
      "[WS] gamePin:",
      gamePin
    );

    console.log(
      "[WS] gamePin type:",
      typeof gamePin
    );

    console.log(
      "[WS] gamePin length:",
      String(gamePin).length
    );

    console.log(
      "[WS] playerToken present:",
      Boolean(playerToken)
    );

    console.log(
      "[WS] hostToken present:",
      Boolean(hostToken)
    );

    console.log(
      "[WS] wsBase:",
      wsBase
    );

    console.log(
      "[WS] Authentication mode:",
      playerToken
        ? "player"
        : hostToken
        ? "host"
        : "none"
    );

    // Never print the real JWT.
    console.log(
      "[WS] Final WebSocket URL:",
      `${wsBase}/ws/game/${gamePin}?${
        playerToken
          ? "player_token=REDACTED"
          : "token=REDACTED"
      }`
    );

    console.log(
      "[WS] Expected route:",
      `/ws/game/${gamePin}`
    );

    console.groupEnd();

    // -------------------------------------------------------
    // CREATE SOCKET
    // -------------------------------------------------------

    const ws = new WebSocket(wsUrl);

    wsRef.current = ws;

    // -------------------------------------------------------
    // OPEN
    // -------------------------------------------------------

    ws.onopen = () => {
      console.log(
        "[WS] Connected successfully"
      );

      connectingRef.current = false;

      setConnecting(false);
      setConnected(true);

      reconnectAttemptsRef.current = 0;
    };

    // -------------------------------------------------------
    // CLOSE
    // -------------------------------------------------------

    ws.onclose = (event) => {
      console.log(
        "[WS] Disconnected:",
        {
          code: event.code,
          reason: event.reason,
          wasClean: event.wasClean,
        }
      );

      connectingRef.current = false;

      setConnected(false);
      setConnecting(false);

      // Check whether this is still the active socket.
      const isActiveSocket =
        wsRef.current === ws;

      // Only clear the reference if this socket is
      // still the active socket.
      if (isActiveSocket) {
        wsRef.current = null;
      }

      // Don't reconnect after intentional disconnect.
      if (
        intentionalDisconnectRef.current
      ) {
        console.log(
          "[WS] Intentional disconnect - skipping reconnect"
        );

        return;
      }

      // An old socket must never start a new connection.
      if (!isActiveSocket) {
        return;
      }

      // -----------------------------------------------------
      // PLAYER AUTO RECONNECT
      // -----------------------------------------------------

      if (
        playerToken &&
        reconnectAttemptsRef.current <
          maxReconnectAttempts
      ) {
        const delay = Math.min(
          1000 *
            2 **
              reconnectAttemptsRef.current,
          10000
        );

        reconnectAttemptsRef.current++;

        console.log(
          `[WS] Reconnecting in ${delay}ms ` +
            `(attempt ${reconnectAttemptsRef.current}/${maxReconnectAttempts})`
        );

        reconnectTimeoutRef.current =
          window.setTimeout(() => {
            reconnectTimeoutRef.current =
              null;

            connect();
          }, delay);
      }
    };

    // -------------------------------------------------------
    // ERROR
    // -------------------------------------------------------

    ws.onerror = (error) => {
      console.error(
        "[WS] WebSocket error:",
        error
      );

      console.error(
        "[WS] Debug information:",
        {
          gamePin,
          wsBase,
          hasPlayerToken:
            Boolean(playerToken),
          hasHostToken:
            Boolean(hostToken),
        }
      );
    };

    // -------------------------------------------------------
    // MESSAGE
    // -------------------------------------------------------

    ws.onmessage = (event) => {
      try {
        console.log(
          "[WS] Message received"
        );

        const envelope: WSEnvelope =
          JSON.parse(event.data);

        handleMessage(envelope);
      } catch (err) {
        console.error(
          "[WS] Failed to parse message:",
          err
        );

        console.error(
          "[WS] Raw message:",
          event.data
        );
      }
    };
  }, [
    gamePin,
    playerToken,
    hostToken,
    handleMessage,
  ]);

  // ---------------------------------------------------------
  // SEND ACTION
  // ---------------------------------------------------------

  const sendAction = useCallback(
    (
      action: WSClientAction,
      payload: Record<string, unknown> = {}
    ) => {
      if (
        wsRef.current?.readyState ===
        WebSocket.OPEN
      ) {
        wsRef.current.send(
          JSON.stringify({
            type: action,
            payload,
          })
        );
      } else {
        console.warn(
          "[WS] Cannot send action, socket is not open"
        );
      }
    },
    []
  );

  // ---------------------------------------------------------
  // PLAYER ACTIONS
  // ---------------------------------------------------------

  const submitAnswer = useCallback(
    (
      questionId: string,
      answerIndex: number
    ) => {
      sendAction(
        WSClientAction.SUBMIT_ANSWER,
        {
          questionId,
          answer: answerIndex,
        }
      );
    },
    [sendAction]
  );

  const requestState = useCallback(() => {
    sendAction(
      WSClientAction.REQUEST_STATE
    );
  }, [sendAction]);

  const ping = useCallback(() => {
    sendAction(
      WSClientAction.PING
    );
  }, [sendAction]);

  // ---------------------------------------------------------
  // HOST ACTIONS
  // ---------------------------------------------------------

  const startGame = useCallback(() => {
    sendAction(
      WSClientAction.START_GAME
    );
  }, [sendAction]);

  const nextQuestion = useCallback(() => {
    sendAction(
      WSClientAction.NEXT_QUESTION
    );
  }, [sendAction]);

  const endQuestion = useCallback(() => {
    sendAction(
      WSClientAction.END_QUESTION
    );
  }, [sendAction]);

  const endGame = useCallback(() => {
    sendAction(
      WSClientAction.END_GAME
    );
  }, [sendAction]);

  const cancelGame = useCallback(() => {
    sendAction(
      WSClientAction.CANCEL_GAME
    );
  }, [sendAction]);

  // ---------------------------------------------------------
  // DISCONNECT
  // ---------------------------------------------------------

  const disconnect = useCallback(() => {
    // Mark this as intentional BEFORE closing the socket.
    // This prevents onclose from starting auto-reconnect.
    intentionalDisconnectRef.current = true;

    // Cancel pending reconnect.
    if (
      reconnectTimeoutRef.current !== null
    ) {
      clearTimeout(
        reconnectTimeoutRef.current
      );

      reconnectTimeoutRef.current = null;
    }

    connectingRef.current = false;

    if (wsRef.current) {
      console.log(
        "[WS] Closing socket manually"
      );

      const socket = wsRef.current;

      // Clear reference first so the close handler
      // cannot treat it as the active socket.
      wsRef.current = null;

      socket.close(
        1000,
        "Client disconnect"
      );
    }

    setConnected(false);
    setConnecting(false);
  }, []);

  // ---------------------------------------------------------
  // RECONNECT
  // ---------------------------------------------------------

  const reconnect = useCallback(() => {
    console.log(
      "[WS] Manual reconnect requested"
    );

    reconnectAttemptsRef.current = 0;

    disconnect();

    window.setTimeout(() => {
      // Manual reconnect is intentional, but the new
      // connection itself should be treated normally.
      intentionalDisconnectRef.current =
        false;

      connect();
    }, 100);
  }, [
    connect,
    disconnect,
  ]);

  // ---------------------------------------------------------
  // CONNECT ON MOUNT / INPUT CHANGE
  // ---------------------------------------------------------

  useEffect(() => {
    console.log(
      "[WS] Hook mounted",
      {
        gamePin,
        hasPlayerToken:
          Boolean(playerToken),
        hasHostToken:
          Boolean(hostToken),
      }
    );

    connect();

    return () => {
      console.log(
        "[WS] Hook unmounting"
      );

      disconnect();
    };
  }, [
    connect,
    disconnect,
  ]);

  // ---------------------------------------------------------
  // HEARTBEAT
  // ---------------------------------------------------------

  useEffect(() => {
    if (!connected) {
      return;
    }

    const interval =
      window.setInterval(() => {
        ping();
      }, 30000);

    return () => {
      clearInterval(interval);
    };
  }, [
    connected,
    ping,
  ]);

  // ---------------------------------------------------------
  // RETURN
  // ---------------------------------------------------------

  return {
    // Connection
    connected,
    connecting,
    role,
    connectionId,

    // Game state
    game,
    players,
    teams,
    currentQuestion,
    reveal,
    leaderboard,
    timeRemainingMs,
    questionStartedAt,
    questionEndsAt,
    alreadyAnswered,
    myResult,
    me,
    canStart,
    serverTime,

    // Actions
    sendAction,
    submitAnswer,
    requestState,
    ping,

    // Host actions
    startGame,
    nextQuestion,
    endQuestion,
    endGame,
    cancelGame,

    // Lifecycle
    disconnect,
    reconnect,
  };
}