import { useRef, useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { ConfirmationResult } from "firebase/auth";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { Card, CardHeader, CardContent, CardFooter } from "../components/ui/Card";
import {
  RECAPTCHA_CONTAINER_ID,
  confirmPhoneCode,
  friendlyAuthError,
  isFirebaseConfigured,
  resetRecaptcha,
  sendPhoneOtp,
} from "../services/firebase";

const firebaseReady = isFirebaseConfigured();

export function LoginPage() {
  const { login, loginWithPhone } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [method, setMethod] = useState<"email" | "phone">("email");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [codeSent, setCodeSent] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const confirmation = useRef<ConfirmationResult | null>(null);

  const from = (location.state as { from?: Location })?.from?.pathname || "/dashboard";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  const handleSendCode = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setNotice("");
    setLoading(true);

    try {
      confirmation.current = await sendPhoneOtp(phone);
      setCodeSent(true);
      setNotice(`Code sent to ${phone}.`);
    } catch (err) {
      resetRecaptcha();
      setError(friendlyAuthError(err));
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyCode = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      if (!confirmation.current) {
        throw new Error("Request a new code first.");
      }
      const idToken = await confirmPhoneCode(confirmation.current, code);
      await loginWithPhone(phone, idToken);
      navigate(from, { replace: true });
    } catch (err) {
      setError(friendlyAuthError(err));
    } finally {
      setLoading(false);
    }
  };

  const handleChangeMethod = (next: "email" | "phone") => {
    setMethod(next);
    setError("");
    setNotice("");
  };

  const handleGoogleLogin = () => {
    // VITE_API_URL already ends in /api, so do not add another one here.
    window.location.href = `${import.meta.env.VITE_API_URL || "http://localhost:8000/api"}/auth/google`;
  };

  return (
    <div className="min-h-[calc(100vh-200px)] flex items-center justify-center px-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <h1 className="text-2xl font-bold">Welcome Back</h1>
          <p className="text-gray-400 mt-1">Sign in to your PLAYOOT IN EVERYWHERE account</p>
        </CardHeader>
        <CardContent>
          {/* Method switch */}
          <div className="grid grid-cols-2 gap-2 mb-6 p-1 bg-gray-800/50 rounded-lg">
            <button
              type="button"
              onClick={() => handleChangeMethod("email")}
              className={`py-2 text-sm font-medium rounded-md transition-colors ${
                method === "email"
                  ? "bg-purple-600 text-white"
                  : "text-gray-400 hover:text-gray-200"
              }`}
            >
              Email
            </button>
            <button
              type="button"
              onClick={() => handleChangeMethod("phone")}
              disabled={!firebaseReady}
              className={`py-2 text-sm font-medium rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                method === "phone"
                  ? "bg-purple-600 text-white"
                  : "text-gray-400 hover:text-gray-200"
              }`}
            >
              Phone
            </button>
          </div>

          {method === "email" ? (
            <form onSubmit={handleSubmit} className="space-y-4">
              <Input
                label="Email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
                autoComplete="email"
                error={error}
              />
              <Input
                label="Password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                autoComplete="current-password"
              />
              <Button type="submit" className="w-full" loading={loading}>
                Sign In
              </Button>
            </form>
          ) : !codeSent ? (
            <form onSubmit={handleSendCode} className="space-y-4">
              <Input
                label="Phone Number"
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+16505550100"
                required
                autoComplete="tel"
                error={error}
              />
              <p className="text-xs text-gray-500">
                Include your country code, e.g. +1 for the USA or +91 for India.
              </p>
              <Button type="submit" className="w-full" loading={loading}>
                Send Code
              </Button>
            </form>
          ) : (
            <form onSubmit={handleVerifyCode} className="space-y-4">
              {notice && (
                <p className="text-sm text-green-400 text-center">{notice}</p>
              )}
              <Input
                label="Verification Code"
                type="text"
                inputMode="numeric"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="123456"
                required
                autoComplete="one-time-code"
                error={error}
              />
              <Button type="submit" className="w-full" loading={loading}>
                Verify and Sign In
              </Button>
              <button
                type="button"
                onClick={() => {
                  setCodeSent(false);
                  setCode("");
                  setError("");
                  setNotice("");
                  confirmation.current = null;
                  resetRecaptcha();
                }}
                className="w-full text-center text-sm text-gray-400 hover:text-gray-200"
              >
                Use a different number
              </button>
            </form>
          )}

          {/* Firebase renders its reCAPTCHA challenge into this container. */}
          <div id={RECAPTCHA_CONTAINER_ID} />

          {/* Divider */}
          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-gray-700" />
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="px-2 bg-gray-900 text-gray-500">Or continue with</span>
            </div>
          </div>

          {/* Google Login */}
          <Button
            type="button"
            variant="outline"
            className="w-full flex items-center justify-center gap-2"
            onClick={handleGoogleLogin}
            disabled={loading}
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24">
              <path
                fill="currentColor"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="currentColor"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="currentColor"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              />
              <path
                fill="currentColor"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 6.23l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              />
            </svg>
            <span>Continue with Google</span>
          </Button>
        </CardContent>
        <CardFooter className="justify-center">
          <p className="text-gray-400 text-sm">
            Don't have an account?{" "}
            <Link to="/register" className="text-purple-400 hover:underline">
              Sign up
            </Link>
          </p>
        </CardFooter>
      </Card>
    </div>
  );
}
