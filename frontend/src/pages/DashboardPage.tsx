import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, QuizSummary } from "../services/api";
import { Button } from "../components/ui/Button";
import {
  Card,
  CardHeader,
  CardContent,
} from "../components/ui/Card";
import { Input } from "../components/ui/Input";

export function DashboardPage() {
  const [quizzes, setQuizzes] = useState<QuizSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newQuizTitle, setNewQuizTitle] = useState("");
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    loadQuizzes();
  }, []);

  const loadQuizzes = async () => {
    try {
      setLoading(true);
      const data = await api.listQuizzes();
      setQuizzes(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load quizzes"
      );
    } finally {
      setLoading(false);
    }
  };

  const handleCreateQuiz = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!newQuizTitle.trim()) return;

    setCreating(true);

    try {
      const quiz = await api.createQuiz({
        title: newQuizTitle.trim(),
        description: null,
        source_type: "manual",
        questions: [],
      });

      setShowCreateModal(false);
      setNewQuizTitle("");

      navigate(`/quiz/${quiz.id}`);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to create quiz"
      );
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteQuiz = async (quizId: number) => {
    if (!confirm("Delete this quiz? This cannot be undone.")) return;

    try {
      await api.deleteQuiz(quizId);
      setQuizzes((prev) => prev.filter((q) => q.id !== quizId));
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to delete quiz"
      );
    }
  };

  return (
    <div className="space-y-8">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">My Quizzes</h1>
          <p className="text-gray-400 mt-1">
            Create, edit, and host your quizzes
          </p>
        </div>

        <div className="flex gap-3">
          <Button onClick={() => setShowCreateModal(true)}>
            New Quiz
          </Button>

          <Button
            variant="outline"
            onClick={() => navigate("/create")}
          >
            AI Generate
          </Button>
        </div>
      </div>

      {error && (
        <div
          className="text-sm text-red-400 p-4 bg-red-900/20 border border-red-900/50 rounded-lg"
          role="alert"
        >
          {error}
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <Card
              key={i}
              variant="outlined"
              className="animate-pulse"
            >
              <CardContent className="py-12">
                <div className="h-6 bg-gray-700 rounded w-3/4 mb-4" />
                <div className="h-4 bg-gray-700 rounded w-1/2 mb-2" />
                <div className="h-4 bg-gray-700 rounded w-1/4" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : quizzes.length === 0 ? (
        <Card
          variant="outlined"
          className="text-center py-16"
        >
          <CardContent>
            <div className="text-5xl mb-4">📝</div>

            <h3 className="text-xl font-semibold mb-2">
              No quizzes yet
            </h3>

            <p className="text-gray-400 mb-6">
              Create your first quiz to get started
            </p>

            <div className="flex gap-3 justify-center">
              <Button
                onClick={() => setShowCreateModal(true)}
              >
                Create Manually
              </Button>

              <Button
                variant="outline"
                onClick={() => navigate("/create")}
              >
                Generate with AI
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {quizzes.map((quiz) => (
            <QuizCard
              key={quiz.id}
              quiz={quiz}
              onDelete={handleDeleteQuiz}
            />
          ))}
        </div>
      )}

      {showCreateModal && (
        <Modal
          isOpen={showCreateModal}
          onClose={() => setShowCreateModal(false)}
          title="Create New Quiz"
        >
          <form
            onSubmit={handleCreateQuiz}
            className="space-y-4"
          >
            <Input
              label="Quiz Title"
              value={newQuizTitle}
              onChange={(e) =>
                setNewQuizTitle(e.target.value)
              }
              placeholder="e.g., JavaScript Fundamentals"
              required
              autoFocus
            />

            <div className="flex justify-end gap-3 pt-4">
              <Button
                type="button"
                variant="outline"
                onClick={() =>
                  setShowCreateModal(false)
                }
              >
                Cancel
              </Button>

              <Button
                type="submit"
                loading={creating}
              >
                Create
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}

function QuizCard({
  quiz,
  onDelete,
}: {
  quiz: QuizSummary;
  onDelete: (id: number) => void;
}) {
  const navigate = useNavigate();

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString(
      undefined,
      {
        month: "short",
        day: "numeric",
        year: "numeric",
      }
    );
  };

  return (
    <Card variant="outlined" className="group">
      <CardContent className="py-6">
        <div className="flex items-start justify-between gap-4 mb-3">
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-lg truncate">
              {quiz.title}
            </h3>

            <p className="text-sm text-gray-500 mt-1">
              {quiz.question_count} questions
            </p>
          </div>

          <span className="px-2 py-1 text-xs font-medium rounded-full bg-purple-600/20 text-purple-400">
            {quiz.source_type}
          </span>
        </div>

        <div className="flex items-center justify-between text-sm text-gray-500 mb-4">
          <span>
            Updated {formatDate(quiz.updated_at)}
          </span>
        </div>

        <div className="flex flex-wrap gap-2">
          <Link
            to={`/quiz/${quiz.id}`}
            className="flex-1 min-w-[5rem]"
          >
            <Button
              variant="outline"
              size="sm"
              className="w-full"
            >
              Edit
            </Button>
          </Link>

          {/* Important:
              Quiz ID routes use /host/quiz/:quizId.
              Game PIN routes use /host/:gamePin.
          */}
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              navigate(`/host/quiz/${quiz.id}`)
            }
          >
            Host
          </Button>

          <Button
            variant="ghost"
            size="sm"
            className="text-red-400 hover:bg-red-900/20"
            onClick={() => onDelete(quiz.id)}
          >
            🗑️
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function Modal({
  isOpen,
  onClose,
  title,
  children,
}: {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) {
  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <Card
        className="w-full max-w-md animate-in slide-in-from-top-4 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        <CardHeader>
          <h2 className="text-xl font-bold">
            {title}
          </h2>
        </CardHeader>

        <CardContent>
          {children}
        </CardContent>
      </Card>
    </div>
  );
}