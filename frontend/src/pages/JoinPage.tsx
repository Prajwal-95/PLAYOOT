import { useState, useEffect } from "react";
import { useNavigate, Link, useSearchParams } from "react-router-dom";
import { api, JoinGameIn, JoinGameOut } from "../services/api";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { Card, CardHeader, CardContent, CardFooter } from "../components/ui/Card";

export function JoinPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [pin, setPin] = useState("");
  const [nickname, setNickname] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Check for PIN in URL params
  useEffect(() => {
    const urlPin = searchParams.get("pin");
    if (urlPin) {
      setPin(urlPin);
    }
  }, [searchParams]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    const cleanPin = pin.replace(/\D/g, "");
    if (cleanPin.length !== 6) {
      setError("Game PIN must be 6 digits");
      return;
    }

    if (nickname.trim().length < 2) {
      setError("Nickname must be at least 2 characters");
      return;
    }

    setLoading(true);
    try {
      const payload: JoinGameIn = {
        nickname: nickname.trim(),
      };
      const result: JoinGameOut = await api.joinGame(cleanPin, payload);
      
      // Store player token and navigate to play page
      localStorage.setItem(`player_token_${cleanPin}`, result.player_token);

      console.log("[JOIN] joinGame success", {
        gamePin: cleanPin,
        hasPlayerToken: Boolean(result.player_token),
      });

      navigate(`/play/${cleanPin}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to join game");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[70vh] flex items-center justify-center px-4 py-8">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="text-5xl mb-4">🎮</div>
          <h1 className="text-2xl font-bold">Join a Game</h1>
          <p className="text-gray-400 mt-1">Enter the 6-digit game PIN from your host</p>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              label="Game PIN"
              type="text"
              value={pin}
              onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 6))}
              placeholder="123456"
              maxLength={6}
              required
              autoComplete="off"
              autoFocus
              className="text-2xl tracking-widest text-center font-mono"
              error={error}
            />
            <Input
              label="Nickname"
              type="text"
              value={nickname}
              onChange={(e) => setNickname(e.target.value)}
              placeholder="Your name"
              maxLength={20}
              required
              autoComplete="name"
            />
            {error && (
              <div className="text-sm text-red-400 p-3 bg-red-900/20 border border-red-900/50 rounded-lg" role="alert">
                {error}
              </div>
            )}
            <Button type="submit" className="w-full" loading={loading} size="lg">
              Join Game
            </Button>
          </form>
        </CardContent>
        <CardFooter className="justify-center">
          <p className="text-gray-400 text-sm">
            Hosting a game? <Link to="/register" className="text-purple-400 hover:underline">Create Quiz</Link>
          </p>
        </CardFooter>
      </Card>
    </div>
  );
}