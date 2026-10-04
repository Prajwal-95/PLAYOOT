import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { api } from "../services/api";
import { Button } from "../components/ui/Button";
import { Card, CardContent } from "../components/ui/Card";

export function AuthCallbackPage() {
  const { login, setUser } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    const handleCallback = async () => {
      const hash = window.location.hash.substring(1);
      const params = new URLSearchParams(hash);
      const accessToken = params.get("access_token");
      const userId = params.get("user_id");

      if (accessToken && userId) {
        localStorage.setItem("access_token", accessToken);
        
        try {
          // Fetch user info
          const user = await api.me();
          // Set user in auth context
          if (setUser) {
            setUser(user);
          } else {
            // Fallback: trigger auth context refresh
            window.dispatchEvent(new CustomEvent("auth-changed"));
          }
          navigate("/dashboard", { replace: true });
        } catch (err) {
          console.error("Failed to fetch user:", err);
          localStorage.removeItem("access_token");
          navigate("/login", { replace: true });
        }
      } else {
        navigate("/login", { replace: true });
      }
    };

    handleCallback();
  }, [navigate]);

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center px-4">
      <Card className="w-full max-w-md">
        <CardContent className="py-12 text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-4 border-purple-600 border-t-transparent mx-auto mb-4" />
          <p className="text-gray-400">Completing sign in...</p>
        </CardContent>
      </Card>
    </div>
  );
}