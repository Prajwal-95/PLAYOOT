import { lazy } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { Layout } from "./components/Layout";
import { HomePage } from "./pages/HomePage";
import { ProtectedRoute } from "./components/ProtectedRoute";

// ---------------------------------------------------------------------------
// Route-level code splitting.
// ---------------------------------------------------------------------------
const LoginPage = lazy(() =>
  import("./pages/LoginPage").then((m) => ({ default: m.LoginPage }))
);

const RegisterPage = lazy(() =>
  import("./pages/RegisterPage").then((m) => ({ default: m.RegisterPage }))
);

const DashboardPage = lazy(() =>
  import("./pages/DashboardPage").then((m) => ({
    default: m.DashboardPage,
  }))
);

const CreateQuizPage = lazy(() =>
  import("./pages/CreateQuizPage").then((m) => ({
    default: m.CreateQuizPage,
  }))
);

const QuizViewPage = lazy(() =>
  import("./pages/QuizViewPage").then((m) => ({
    default: m.QuizViewPage,
  }))
);

const JoinPage = lazy(() =>
  import("./pages/JoinPage").then((m) => ({ default: m.JoinPage }))
);

const HostLobbyPage = lazy(() =>
  import("./pages/HostLobbyPage").then((m) => ({
    default: m.HostLobbyPage,
  }))
);

const PlayPage = lazy(() =>
  import("./pages/PlayPage").then((m) => ({ default: m.PlayPage }))
);

const ResultsPage = lazy(() =>
  import("./pages/ResultsPage").then((m) => ({
    default: m.ResultsPage,
  }))
);

const AuthCallbackPage = lazy(() =>
  import("./pages/AuthCallbackPage").then((m) => ({
    default: m.AuthCallbackPage,
  }))
);

function AppRoutes() {
  const { loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-950">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-purple-600 border-t-transparent" />
      </div>
    );
  }

  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<HomePage />} />

        <Route path="login" element={<LoginPage />} />
        <Route path="register" element={<RegisterPage />} />
        <Route path="join" element={<JoinPage />} />

        <Route path="play/:gamePin" element={<PlayPage />} />
        <Route path="results/:gamePin" element={<ResultsPage />} />

        <Route path="auth/callback" element={<AuthCallbackPage />} />

        {/* Protected routes */}
        <Route element={<ProtectedRoute />}>
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="create" element={<CreateQuizPage />} />
          <Route path="quiz/:quizId" element={<QuizViewPage />} />

          {/* IMPORTANT:
              /host/quiz/:quizId = create a new game from a quiz
              /host/:gamePin     = open an existing game lobby
          */}
          <Route
            path="host/quiz/:quizId"
            element={<HostLobbyPage />}
          />

          <Route
            path="host/:gamePin"
            element={<HostLobbyPage />}
          />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;