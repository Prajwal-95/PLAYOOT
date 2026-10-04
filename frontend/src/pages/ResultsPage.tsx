import { useState, useEffect } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { api, GameResults } from "../services/api";
import { Button } from "../components/ui/Button";
import { Card, CardHeader, CardContent, CardFooter } from "../components/ui/Card";
import { GameState, Leaderboard, LeaderboardEntry } from "../types/game";
import { cn } from "../utils/cn";

export function ResultsPage() {
  const { gamePin } = useParams<{ gamePin: string }>();
  const navigate = useNavigate();
  const [results, setResults] = useState<GameResults | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (gamePin) {
      loadResults();
    }
  }, [gamePin]);

  const loadResults = async () => {
    try {
      setLoading(true);
      const data = await api.getResults(gamePin!);
      setResults(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load results");
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-12">
        <div className="animate-pulse space-y-6">
          <div className="h-8 bg-gray-800 rounded w-1/4" />
          <Card variant="outlined"><CardContent className="py-12"><div className="h-6 bg-gray-700 rounded w-3/4" /></CardContent></Card>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-12 text-center">
        <Card variant="outlined">
          <CardContent className="py-12">
            <div className="text-5xl mb-4">⚠️</div>
            <h2 className="text-xl font-bold mb-2">Unable to Load Results</h2>
            <p className="text-gray-400 mb-6">{error}</p>
            <Button variant="outline" onClick={() => navigate("/join")}>Back to Join</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!results) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-12 text-center">
        <Card variant="outlined">
          <CardContent className="py-12">
            <div className="text-5xl mb-4">📊</div>
            <h2 className="text-xl font-bold mb-2">No Results Available</h2>
            <p className="text-gray-400 mb-6">This game may not have finished yet.</p>
            <Button variant="outline" onClick={() => navigate("/join")}>Back to Join</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Type assertion for the results structure
  const gameResults = results as unknown as {
    game: {
      gameId: number;
      gamePin: string;
      mode: string;
      quizTitle: string;
      totalQuestions: number;
      endedAt: string;
    };
    finalLeaderboard: Leaderboard;
    playerResults?: Array<{
      playerId: number;
      nickname: string;
      score: number;
      rank: number;
      correctAnswers: number;
      totalAnswers: number;
      averageResponseTime: number;
    }>;
    teamResults?: Array<{
      teamId: number;
      name: string;
      score: number;
      rank: number;
      members: Array<{
        playerId: number;
        nickname: string;
        score: number;
      }>;
    }>;
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      <div className="text-center">
        <h1 className="text-4xl font-bold mb-2">🏆 Game Results</h1>
        <p className="text-gray-400">{gameResults.game?.quizTitle || "Quiz"}</p>
        <div className="flex items-center justify-center gap-6 mt-4 text-sm text-gray-500">
          <span>PIN: <span className="font-mono font-bold text-purple-400">{gameResults.game?.gamePin}</span></span>
          <span>Mode: {gameResults.game?.mode === "team" ? "👥 Team" : "👤 Individual"}</span>
          <span>Questions: {gameResults.game?.totalQuestions}</span>
          <span>Ended: {gameResults.game?.endedAt ? new Date(gameResults.game.endedAt).toLocaleString() : "Unknown"}</span>
        </div>
      </div>

      {/* Final Leaderboard */}
      <Card variant="outlined">
        <CardHeader>
          <h2 className="text-xl font-semibold">
            {gameResults.finalLeaderboard?.mode === "team" ? "👥 Final Team Standings" : "🏆 Final Leaderboard"}
          </h2>
        </CardHeader>
        <CardContent>
          {gameResults.finalLeaderboard?.entries.length > 0 ? (
            <div className="space-y-2">
              {gameResults.finalLeaderboard.entries.map((entry: LeaderboardEntry) => (
                <div 
                  key={entry.id} 
                  className={cn(
                    "flex items-center justify-between p-4 rounded-lg transition-colors",
                    entry.rank === 1 && "bg-yellow-900/20 border border-yellow-500/30",
                    entry.rank === 2 && "bg-gray-800/50 border border-gray-500/30",
                    entry.rank === 3 && "bg-amber-900/20 border border-amber-500/30",
                    "bg-gray-800/50 hover:bg-gray-700/50"
                  )}
                >
                  <div className="flex items-center gap-4">
                    <span className={cn(
                      "w-12 h-12 rounded-full flex items-center justify-center font-bold text-lg flex-shrink-0",
                      entry.rank === 1 ? "bg-yellow-500 text-black text-xl" :
                      entry.rank === 2 ? "bg-gray-400 text-black text-xl" :
                      entry.rank === 3 ? "bg-amber-700 text-white text-xl" :
                      "bg-gray-700 text-gray-300"
                    )}>
                      #{entry.rank}
                    </span>
                    <div>
                      <p className="font-semibold text-lg">{entry.name}</p>
                      {gameResults.finalLeaderboard.mode === "team" && entry.memberCount && (
                        <p className="text-sm text-gray-500">{entry.memberCount} members</p>
                      )}
                      {entry.members && entry.members.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {entry.members.map((member) => (
                            <span key={member.playerId} className="px-2 py-0.5 text-xs bg-gray-700 rounded">
                              {member.nickname}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    <span className="font-bold text-purple-400 text-2xl">{entry.score}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-gray-500">
              No results available
            </div>
          )}
        </CardContent>
      </Card>

      {/* Player Stats (Individual Mode) */}
      {gameResults.game?.mode === "individual" && gameResults.playerResults && gameResults.playerResults.length > 0 && (
        <Card variant="outlined">
          <CardHeader>
            <h2 className="text-xl font-semibold">📊 Player Statistics</h2>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-gray-700 text-gray-500 text-sm">
                    <th className="pb-2 pr-4">Rank</th>
                    <th className="pb-2 pr-4">Player</th>
                    <th className="pb-2 pr-4">Score</th>
                    <th className="pb-2 pr-4">Correct</th>
                    <th className="pb-2 pr-4">Accuracy</th>
                    <th className="pb-2">Avg Response</th>
                  </tr>
                </thead>
                <tbody>
                  {gameResults.playerResults
                    .sort((a, b) => a.rank - b.rank)
                    .map((player) => (
                    <tr key={player.playerId} className="border-b border-gray-800 hover:bg-gray-800/50">
                      <td className="py-3 pr-4 font-bold">
                        {player.rank === 1 && "🥇"}
                        {player.rank === 2 && "🥈"}
                        {player.rank === 3 && "🥉"}
                        {player.rank > 3 && `#${player.rank}`}
                      </td>
                      <td className="py-3 pr-4 font-medium">{player.nickname}</td>
                      <td className="py-3 pr-4 font-bold text-purple-400">{player.score}</td>
                      <td className="py-3 pr-4">{player.correctAnswers}/{player.totalAnswers}</td>
                      <td className="py-3 pr-4">
                        {player.totalAnswers > 0 
                          ? `${Math.round((player.correctAnswers / player.totalAnswers) * 100)}%`
                          : "N/A"}
                      </td>
                      <td className="py-3">{player.averageResponseTime}ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Team Details (Team Mode) */}
      {gameResults.game?.mode === "team" && gameResults.teamResults && gameResults.teamResults.length > 0 && (
        <Card variant="outlined">
          <CardHeader>
            <h2 className="text-xl font-semibold">👥 Team Details</h2>
          </CardHeader>
          <CardContent>
            <div className="space-y-6">
              {gameResults.teamResults
                .sort((a, b) => a.rank - b.rank)
                .map((team) => (
                <div key={team.teamId} className="p-4 bg-gray-800/50 rounded-lg">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <span className={cn(
                        "w-10 h-10 rounded-full flex items-center justify-center font-bold text-lg",
                        team.rank === 1 ? "bg-yellow-500 text-black" :
                        team.rank === 2 ? "bg-gray-400 text-black" :
                        team.rank === 3 ? "bg-amber-700 text-white" :
                        "bg-gray-700 text-gray-300"
                      )}>
                        #{team.rank}
                      </span>
                      <div>
                        <h3 className="font-semibold text-lg">{team.name}</h3>
                        <p className="text-sm text-gray-500">{team.members.length} members</p>
                      </div>
                    </div>
                    <span className="font-bold text-purple-400 text-2xl">{team.score}</span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                    {team.members.map((member) => (
                      <div key={member.playerId} className="p-3 bg-gray-900/50 rounded-lg">
                        <p className="font-medium">{member.nickname}</p>
                        <p className="text-sm text-purple-400 font-bold">{member.score} pts</p>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Actions */}
      <div className="flex flex-col sm:flex-row gap-4 justify-center">
        <Link to="/join">
          <Button variant="outline" className="w-full sm:w-auto">Join Another Game</Button>
        </Link>
        <Link to="/dashboard">
          <Button variant="secondary" className="w-full sm:w-auto">Back to Dashboard</Button>
        </Link>
      </div>
    </div>
  );
}