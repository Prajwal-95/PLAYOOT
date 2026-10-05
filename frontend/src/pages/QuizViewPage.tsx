import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, Quiz, QuestionOut } from "../services/api";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import {
  Card,
  CardHeader,
  CardContent,
} from "../components/ui/Card";
import { cn } from "../utils/cn";

interface QuestionForm {
  question_text: string;
  options: string[];
  correct_answer: string;
  explanation: string;
  time_limit: number;
  points: number;
}

export function QuizViewPage() {
  const { quizId } = useParams<{ quizId: string }>();
  const navigate = useNavigate();

  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [editingIndex, setEditingIndex] = useState<number | null>(null);

  const [editForm, setEditForm] = useState<QuestionForm>({
    question_text: "",
    options: ["", "", "", ""],
    correct_answer: "",
    explanation: "",
    time_limit: 20,
    points: 1000,
  });

  useEffect(() => {
    if (quizId) {
      loadQuiz();
    }
  }, [quizId]);

  const loadQuiz = async () => {
    try {
      setLoading(true);

      const data = await api.getQuiz(
        parseInt(quizId!)
      );

      setQuiz(data);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to load quiz"
      );
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateQuiz = async (
    e: React.FormEvent
  ) => {
    e.preventDefault();

    if (!quiz) return;

    setSaving(true);

    try {
      await api.updateQuiz(quiz.id, {
        title: quiz.title,
        description: quiz.description,
        questions: quiz.questions,
      });

      setError("");
      alert("Quiz saved!");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to save quiz"
      );
    } finally {
      setSaving(false);
    }
  };

  const handleAddQuestion = () => {
    if (!quiz) return;

    const newQuestion: QuestionOut = {
      id: Date.now(),
      question_text: "",
      options: ["", "", "", ""],
      correct_answer: "",
      explanation: null,
      time_limit: 20,
      points: 1000,
      order_index: quiz.questions.length,
    };

    setQuiz((prev) =>
      prev
        ? {
            ...prev,
            questions: [
              ...prev.questions,
              newQuestion,
            ],
          }
        : null
    );

    setEditingIndex(quiz.questions.length);

    setEditForm({
      question_text: "",
      options: ["", "", "", ""],
      correct_answer: "",
      explanation: "",
      time_limit: 20,
      points: 1000,
    });
  };

  const handleEditQuestion = (
    index: number
  ) => {
    if (!quiz) return;

    const q = quiz.questions[index];

    setEditingIndex(index);

    setEditForm({
      question_text: q.question_text,
      options: [...q.options],
      correct_answer: q.correct_answer,
      explanation: q.explanation || "",
      time_limit: q.time_limit,
      points: q.points,
    });
  };

  const handleSaveEdit = (
    index: number
  ) => {
    if (!quiz) return;

    const updatedQuestions = [
      ...quiz.questions,
    ];

    updatedQuestions[index] = {
      ...updatedQuestions[index],
      ...editForm,
      options: editForm.options.filter(
        (o) => o.trim()
      ),
    } as QuestionOut;

    setQuiz((prev) =>
      prev
        ? {
            ...prev,
            questions: updatedQuestions,
          }
        : null
    );

    setEditingIndex(null);
  };

  const handleDeleteQuestion = (
    index: number
  ) => {
    if (!quiz) return;

    if (!confirm("Delete this question?")) {
      return;
    }

    const updatedQuestions = quiz.questions
      .filter((_, i) => i !== index)
      .map((q, i) => ({
        ...q,
        order_index: i,
      }));

    setQuiz((prev) =>
      prev
        ? {
            ...prev,
            questions: updatedQuestions,
          }
        : null
    );
  };

  const handleQuestionTextChange = (
    index: number,
    value: string
  ) => {
    if (editingIndex === index) {
      setEditForm((prev) => ({
        ...prev,
        question_text: value,
      }));
    } else if (quiz) {
      const updatedQuestions = [
        ...quiz.questions,
      ];

      updatedQuestions[index] = {
        ...updatedQuestions[index],
        question_text: value,
      };

      setQuiz((prev) =>
        prev
          ? {
              ...prev,
              questions: updatedQuestions,
            }
          : null
      );
    }
  };

  const handleOptionChange = (
    questionIndex: number,
    optionIndex: number,
    value: string
  ) => {
    if (editingIndex === questionIndex) {
      setEditForm((prev) => ({
        ...prev,
        options: prev.options.map(
          (o, i) =>
            i === optionIndex ? value : o
        ),
      }));
    } else if (quiz) {
      const updatedQuestions = [
        ...quiz.questions,
      ];

      updatedQuestions[questionIndex] = {
        ...updatedQuestions[questionIndex],
        options:
          updatedQuestions[
            questionIndex
          ].options.map(
            (o, i) =>
              i === optionIndex ? value : o
          ),
      };

      setQuiz((prev) =>
        prev
          ? {
              ...prev,
              questions: updatedQuestions,
            }
          : null
      );
    }
  };

  const handleCorrectAnswerChange = (
    questionIndex: number,
    answer: string
  ) => {
    if (editingIndex === questionIndex) {
      setEditForm((prev) => ({
        ...prev,
        correct_answer: answer,
      }));
    } else if (quiz) {
      const updatedQuestions = [
        ...quiz.questions,
      ];

      updatedQuestions[questionIndex] = {
        ...updatedQuestions[questionIndex],
        correct_answer: answer,
      };

      setQuiz((prev) =>
        prev
          ? {
              ...prev,
              questions: updatedQuestions,
            }
          : null
      );
    }
  };

  const handleAddOption = (
    questionIndex: number
  ) => {
    if (editingIndex === questionIndex) {
      setEditForm((prev) => ({
        ...prev,
        options: [...prev.options, ""],
      }));
    } else if (quiz) {
      const updatedQuestions = [
        ...quiz.questions,
      ];

      updatedQuestions[questionIndex] = {
        ...updatedQuestions[questionIndex],
        options: [
          ...updatedQuestions[
            questionIndex
          ].options,
          "",
        ],
      };

      setQuiz((prev) =>
        prev
          ? {
              ...prev,
              questions: updatedQuestions,
            }
          : null
      );
    }
  };

  const handleTimeLimitChange = (
    index: number,
    value: number
  ) => {
    if (editingIndex === index) {
      setEditForm((prev) => ({
        ...prev,
        time_limit: value,
      }));
    } else if (quiz) {
      const updatedQuestions = [
        ...quiz.questions,
      ];

      updatedQuestions[index] = {
        ...updatedQuestions[index],
        time_limit: value,
      };

      setQuiz((prev) =>
        prev
          ? {
              ...prev,
              questions: updatedQuestions,
            }
          : null
      );
    }
  };

  const handlePointsChange = (
    index: number,
    value: number
  ) => {
    if (editingIndex === index) {
      setEditForm((prev) => ({
        ...prev,
        points: value,
      }));
    } else if (quiz) {
      const updatedQuestions = [
        ...quiz.questions,
      ];

      updatedQuestions[index] = {
        ...updatedQuestions[index],
        points: value,
      };

      setQuiz((prev) =>
        prev
          ? {
              ...prev,
              questions: updatedQuestions,
            }
          : null
      );
    }
  };

  const handleExplanationChange = (
    index: number,
    value: string
  ) => {
    if (editingIndex === index) {
      setEditForm((prev) => ({
        ...prev,
        explanation: value,
      }));
    } else if (quiz) {
      const updatedQuestions = [
        ...quiz.questions,
      ];

      updatedQuestions[index] = {
        ...updatedQuestions[index],
        explanation: value,
      };

      setQuiz((prev) =>
        prev
          ? {
              ...prev,
              questions: updatedQuestions,
            }
          : null
      );
    }
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto">
        <div className="animate-pulse space-y-6">
          <div className="h-8 bg-gray-800 rounded w-1/4" />

          <Card variant="outlined">
            <CardContent className="py-12">
              <div className="h-6 bg-gray-700 rounded w-3/4" />
            </CardContent>
          </Card>

          <Card variant="outlined">
            <CardContent className="py-12">
              <div className="h-6 bg-gray-700 rounded w-3/4" />
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  if (!quiz) {
    return (
      <div className="max-w-4xl mx-auto text-center py-16">
        <h2 className="text-xl font-semibold">
          Quiz not found
        </h2>

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

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">
            {quiz.title}
          </h1>

          <p className="text-gray-400">
            {quiz.questions.length} questions •{" "}
            {quiz.source_type}
          </p>
        </div>

        <div className="flex gap-3">
          <Button
            variant="outline"
            onClick={() =>
              navigate("/dashboard")
            }
          >
            Back
          </Button>

          {/* Important:
              This route explicitly identifies the parameter
              as a quiz ID rather than a game PIN.
          */}
          <Button
            variant="outline"
            onClick={() =>
              navigate(`/host/quiz/${quiz.id}`)
            }
          >
            Host Game
          </Button>

          <Button
            onClick={handleUpdateQuiz}
            loading={saving}
          >
            Save Changes
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

      <Card variant="outlined">
        <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <h2 className="text-xl font-semibold">
            Questions ({quiz.questions.length})
          </h2>

          <Button onClick={handleAddQuestion}>
            Add Question
          </Button>
        </CardHeader>

        <CardContent>
          {quiz.questions.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              <p>
                No questions yet. Click "Add Question"
                to create one.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {quiz.questions.map(
                (q, index) => (
                  <QuestionCard
                    key={q.id}
                    question={q}
                    index={index}
                    isEditing={
                      editingIndex === index
                    }
                    editForm={
                      editingIndex === index
                        ? editForm
                        : null
                    }
                    onQuestionTextChange={
                      handleQuestionTextChange
                    }
                    onOptionChange={
                      handleOptionChange
                    }
                    onCorrectAnswerChange={
                      handleCorrectAnswerChange
                    }
                    onAddOption={
                      handleAddOption
                    }
                    onTimeLimitChange={
                      handleTimeLimitChange
                    }
                    onPointsChange={
                      handlePointsChange
                    }
                    onExplanationChange={
                      handleExplanationChange
                    }
                    onEdit={() =>
                      handleEditQuestion(index)
                    }
                    onSave={() =>
                      handleSaveEdit(index)
                    }
                    onCancel={() =>
                      setEditingIndex(null)
                    }
                    onDelete={() =>
                      handleDeleteQuestion(index)
                    }
                  />
                )
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

interface QuestionCardProps {
  question: QuestionOut;
  index: number;
  isEditing: boolean;
  editForm: QuestionForm | null;
  onQuestionTextChange: (
    qIndex: number,
    value: string
  ) => void;
  onOptionChange: (
    qIndex: number,
    oIndex: number,
    value: string
  ) => void;
  onCorrectAnswerChange: (
    qIndex: number,
    answer: string
  ) => void;
  onAddOption: (
    qIndex: number
  ) => void;
  onTimeLimitChange: (
    qIndex: number,
    value: number
  ) => void;
  onPointsChange: (
    qIndex: number,
    value: number
  ) => void;
  onExplanationChange: (
    qIndex: number,
    value: string
  ) => void;
  onEdit: () => void;
  onSave: (index: number) => void;
  onCancel: () => void;
  onDelete: () => void;
}

function QuestionCard({
  question,
  index,
  isEditing,
  editForm,
  onQuestionTextChange,
  onOptionChange,
  onCorrectAnswerChange,
  onAddOption,
  onTimeLimitChange,
  onPointsChange,
  onExplanationChange,
  onEdit,
  onSave,
  onCancel,
  onDelete,
}: QuestionCardProps) {
  const form = editForm || question;

  const options = form.options.filter(
    (o) => o.trim()
  );

  return (
    <Card
      variant="outlined"
      className={cn(
        isEditing && "ring-2 ring-purple-500"
      )}
    >
      <CardContent className="py-4">
        <div className="flex items-start justify-between gap-4 mb-3">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <span className="text-2xl font-bold text-purple-400 w-10 text-center">
              Q{index + 1}
            </span>

            <div className="flex-1 min-w-0">
              {isEditing ? (
                <textarea
                  value={form.question_text}
                  onChange={(e) =>
                    onQuestionTextChange(
                      index,
                      e.target.value
                    )
                  }
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none"
                  rows={2}
                  placeholder="Enter question text..."
                />
              ) : (
                <p className="font-medium text-lg">
                  {question.question_text || (
                    <span className="text-gray-500 italic">
                      Empty question
                    </span>
                  )}
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {isEditing ? (
              <>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() =>
                    onSave(index)
                  }
                >
                  Save
                </Button>

                <Button
                  size="sm"
                  variant="ghost"
                  onClick={onCancel}
                >
                  Cancel
                </Button>
              </>
            ) : (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={onEdit}
                >
                  Edit
                </Button>

                <Button
                  size="sm"
                  variant="ghost"
                  className="text-red-400 hover:bg-red-900/20"
                  onClick={onDelete}
                >
                  Delete
                </Button>
              </>
            )}
          </div>
        </div>

        <div className="space-y-2 ml-10">
          {options.map(
            (opt, optIndex) => (
              <label
                key={optIndex}
                className="flex items-center gap-3 p-3 bg-gray-800/50 rounded-lg cursor-pointer hover:bg-gray-700/50 transition-colors"
              >
                <input
                  type="radio"
                  name={`correct-${question.id}`}
                  checked={
                    opt === form.correct_answer
                  }
                  onChange={() =>
                    onCorrectAnswerChange(
                      index,
                      opt
                    )
                  }
                  className="text-purple-600 focus:ring-purple-500 h-4 w-4"
                />

                {isEditing ? (
                  <input
                    type="text"
                    value={opt}
                    onChange={(e) =>
                      onOptionChange(
                        index,
                        optIndex,
                        e.target.value
                      )
                    }
                    className="flex-1 px-3 py-2 bg-gray-900 border border-gray-600 rounded text-white focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                  />
                ) : (
                  <span className="flex-1">
                    {opt || (
                      <span className="text-gray-500 italic">
                        Empty option
                      </span>
                    )}
                  </span>
                )}

                {opt === form.correct_answer && (
                  <span className="text-xs px-2 py-1 bg-green-900/30 text-green-400 rounded-full">
                    Correct
                  </span>
                )}
              </label>
            )
          )}

          {isEditing &&
            options.length < 6 && (
              <Button
                size="sm"
                variant="outline"
                onClick={() =>
                  onAddOption(index)
                }
                className="w-full justify-start"
              >
                + Add Option
              </Button>
            )}

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2">
            <Input
              label="Time Limit (s)"
              type="number"
              value={form.time_limit}
              onChange={(e) =>
                onTimeLimitChange(
                  index,
                  Math.max(
                    5,
                    Math.min(
                      300,
                      parseInt(
                        e.target.value
                      ) || 5
                    )
                  )
                )
              }
              min={5}
              max={300}
            />

            <Input
              label="Points"
              type="number"
              value={form.points}
              onChange={(e) =>
                onPointsChange(
                  index,
                  Math.max(
                    0,
                    Math.min(
                      100000,
                      parseInt(
                        e.target.value
                      ) || 1000
                    )
                  )
                )
              }
              min={0}
              max={100000}
            />

            <div className="md:col-span-3">
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Explanation
              </label>

              <textarea
                value={form.explanation || ""}
                onChange={(e) =>
                  onExplanationChange(
                    index,
                    e.target.value
                  )
                }
                placeholder="Optional explanation shown after answer is revealed"
                rows={2}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none"
              />
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}