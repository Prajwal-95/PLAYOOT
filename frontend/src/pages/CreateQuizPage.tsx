import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  api,
  clampInt,
  GenerateQuizIn,
  GenerateQuizOut,
  MAX_GENERATED_QUESTIONS,
  MAX_OPTION_COUNT,
  MIN_GENERATED_QUESTIONS,
  MIN_OPTION_COUNT,
  OPTION_COUNTS,
  POINTS_MAX,
  POINTS_MIN,
  POINTS_PRESETS,
  QuestionIn,
  TIMER_MAX,
  TIMER_MIN,
  TIMER_PRESETS,
} from "../services/api";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { ScrollSelect } from "../components/ui/ScrollSelect";
import { SelectWithCustom } from "../components/ui/SelectWithCustom";
import { Card, CardContent } from "../components/ui/Card";
import { CollapsibleSection } from "../components/ui/Collapsible";
import { cn } from "../utils/cn";

const SOURCE_META = {
  topic: { icon: "📚", label: "Topic", desc: "e.g. World Capitals" },
  prompt: { icon: "✍️", label: "Prompt", desc: "Describe it in detail" },
  pdf: { icon: "📄", label: "PDF", desc: "Upload a document" },
} as const;

const DIFFICULTY_OPTIONS = ["easy", "medium", "hard", "mixed"] as const;

export function CreateQuizPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState<"config" | "review">("config");

  // Generation config
  const [sourceType, setSourceType] = useState<"topic" | "prompt" | "pdf">("topic");
  const [topic, setTopic] = useState("");
  const [prompt, setPrompt] = useState("");
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [questionCount, setQuestionCount] = useState(5);
  const [optionCount, setOptionCount] = useState(4);
  const [difficulty, setDifficulty] = useState<"easy" | "medium" | "hard" | "mixed">("mixed");
  const [timeLimit, setTimeLimit] = useState(20);
  const [points, setPoints] = useState(1000);
  const [save, setSave] = useState(true);
  const [questionTypes, setQuestionTypes] = useState<GenerateQuizIn["question_types"]>(["multiple_choice"]);
  const [customInstructions, setCustomInstructions] = useState("");
  const [winnersCount, setWinnersCount] = useState<1 | 3 | 5 | 10>(3);

  // Generated questions
  const [generatedQuestions, setGeneratedQuestions] = useState<GenerateQuizOut["questions"]>([]);
  const [generatedQuiz, setGeneratedQuiz] = useState<GenerateQuizOut["quiz"] | null>(null);

  // State
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    // Mirror the backend bounds so a bad value never costs an AI round-trip.
    if (questionCount < MIN_GENERATED_QUESTIONS || questionCount > MAX_GENERATED_QUESTIONS) {
      setError(`Number of Questions must be between ${MIN_GENERATED_QUESTIONS} and ${MAX_GENERATED_QUESTIONS}.`);
      return;
    }
    if (optionCount < MIN_OPTION_COUNT || optionCount > MAX_OPTION_COUNT) {
      setError(`Options per Question must be between ${MIN_OPTION_COUNT} and ${MAX_OPTION_COUNT}.`);
      return;
    }
    if (timeLimit < TIMER_MIN || timeLimit > TIMER_MAX) {
      setError(`Time Limit must be between ${TIMER_MIN} and ${TIMER_MAX} seconds.`);
      return;
    }

    setLoading(true);

    try {
      let result: GenerateQuizOut;

      if (sourceType === "pdf" && pdfFile) {
        const formData = new FormData();
        formData.append("file", pdfFile);
        formData.append("title", title || pdfFile.name);
        formData.append("question_count", String(questionCount));
        formData.append("option_count", String(optionCount));
        formData.append("difficulty", difficulty);
        formData.append("time_limit", String(timeLimit));
        formData.append("points", String(points));
        formData.append("save", String(save));
        formData.append("question_types", JSON.stringify(questionTypes));
        formData.append("custom_instructions", customInstructions);
        formData.append("winners_count", String(winnersCount));

        result = await api.generateQuizFromPdf(formData);
      } else {
        const payload: GenerateQuizIn = {
          source_type: sourceType === "pdf" ? "topic" : sourceType,
          topic: sourceType === "topic" ? topic : undefined,
          prompt: sourceType === "prompt" ? prompt : undefined,
          title: title || undefined,
          question_count: questionCount,
          question_types: questionTypes,
          option_count: optionCount,
          difficulty,
          time_limit: timeLimit,
          points,
          save,
          custom_instructions: customInstructions || undefined,
          winners_count: winnersCount,
        };

        result = await api.generateQuiz(payload);
      }

      setGeneratedQuestions(result.questions);
      setGeneratedQuiz(result.quiz);
      setStep("review");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!generatedQuiz) return;

    setSaving(true);
    try {
      // The quiz is already saved if save=true, otherwise we need to create it
      if (save && generatedQuiz.id) {
        navigate(`/quiz/${generatedQuiz.id}`);
      } else {
        // Create quiz from generated questions
        const questions: QuestionIn[] = generatedQuestions.map((q) => ({
          question_text: q.question_text,
          options: q.options,
          correct_answer: q.correct_answer,
          explanation: q.explanation,
          time_limit: q.time_limit,
          points: q.points,
        }));

        const quiz = await api.createQuiz({
          title: generatedQuiz.title || title || "Generated Quiz",
          description: `Generated from ${sourceType}`,
          source_type: sourceType,
          questions,
        });

        navigate(`/quiz/${quiz.id}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save quiz");
    } finally {
      setSaving(false);
    }
  };

  const handleEditQuestion = (index: number, field: keyof QuestionIn, value: string | string[]) => {
    setGeneratedQuestions((prev) =>
      prev.map((q, i) => (i === index ? { ...q, [field]: value } : q))
    );
  };

  const toggleQuestionType = (type: NonNullable<GenerateQuizIn["question_types"]>[number]) => {
    setQuestionTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    );
  };


  if (step === "review") {
    return (
      <div className="max-w-4xl mx-auto space-y-8">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="space-y-1">
            <span className="inline-flex items-center gap-2 glass-card rounded-full px-3 py-1 text-xs uppercase tracking-widest text-purple-200">
              ✨ Review
            </span>
            <h1 className="text-3xl font-bold page-title">Review Generated Questions</h1>
            <p className="text-gray-400">Edit any question before saving.</p>
          </div>
          <Button variant="outline" onClick={() => setStep("config")}>
            ← Back to settings
          </Button>
        </div>

        {error && (
          <div className="text-sm text-red-300 p-4 glass-card border-red-500/30 rounded-xl" role="alert">
            {error}
          </div>
        )}

        <div className="space-y-4">
          {generatedQuestions.map((q, index) => (
            <Card key={index} variant="glass">
              <CardContent className="py-5">
                <div className="flex items-start justify-between gap-4 mb-3">
                  <h3 className="font-semibold flex-1 text-white">
                    <span className="text-purple-300">Q{index + 1}.</span> {q.question_text}
                  </h3>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mb-3">
                  {q.options.map((opt, optIndex) => {
                    const isCorrect = opt === q.correct_answer;
                    return (
                      <label
                        key={optIndex}
                        className={cn(
                          "flex items-center gap-2 p-2.5 rounded-xl cursor-pointer border transition-colors",
                          isCorrect
                            ? "border-emerald-500/50 bg-emerald-500/10"
                            : "border-white/10 bg-white/5 hover:bg-white/10"
                        )}
                      >
                        <input
                          type="radio"
                          name={`correct-${index}`}
                          checked={isCorrect}
                          onChange={() => handleEditQuestion(index, "correct_answer", opt)}
                          className="text-purple-600 focus:ring-purple-500"
                        />
                        <span className="text-sm">{opt}</span>
                      </label>
                    );
                  })}
                </div>
                <div className="flex flex-wrap gap-4 text-sm text-gray-400">
                  <span className="inline-flex items-center gap-1">⏱️ {q.time_limit}s</span>
                  <span className="inline-flex items-center gap-1">🏆 {q.points} pts</span>
                  {q.explanation && <span className="flex-1 truncate">💡 {q.explanation}</span>}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        <Card variant="glass">
          <CardContent className="py-5">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <label className="flex items-center gap-2 cursor-pointer text-sm text-gray-300">
                <input
                  type="checkbox"
                  checked={save}
                  onChange={(e) => setSave(e.target.checked)}
                  className="text-purple-600 focus:ring-purple-500"
                />
                Save quiz to dashboard
              </label>
              <div className="flex gap-3">
                <Button variant="outline" onClick={() => setStep("config")}>Regenerate</Button>
                <Button variant="rainbow" loading={saving} onClick={handleSave}>
                  {saving ? "Saving..." : "Save Quiz"}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }


  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Header */}
      <header className="text-center space-y-4">
        <span className="inline-flex items-center gap-2 glass-card rounded-full px-4 py-2 text-xs uppercase tracking-[0.2em] text-purple-200">
          <span>✨</span> AI Quiz Builder
        </span>
        <h1 className="text-4xl md:text-5xl font-bold page-title">
          <span className="gradient-text">Create Quiz with AI</span>
        </h1>
        <p className="text-gray-400 max-w-xl mx-auto">
          Generate a polished quiz from a topic, a detailed prompt, or a PDF — then fine-tune
          every setting below.
        </p>
      </header>

      {error && (
        <div className="text-sm text-red-300 p-4 glass-card border-red-500/30 rounded-xl" role="alert">
          {error}
        </div>
      )}

      {/* Source */}
      <section className="glass-card rounded-2xl p-6 sm:p-8 space-y-6">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-purple-500/25 to-fuchsia-500/25 text-xl">
            📚
          </span>
          <div>
            <h2 className="font-semibold text-white text-lg">What should the quiz be about?</h2>
            <p className="text-xs text-gray-400">Pick a source, then describe it below.</p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {(["topic", "prompt", "pdf"] as const).map((type) => {
            const meta = SOURCE_META[type];
            const active = sourceType === type;
            return (
              <label key={type} className="cursor-pointer">
                <input
                  type="radio"
                  name="sourceType"
                  value={type}
                  checked={active}
                  onChange={() => setSourceType(type)}
                  className="sr-only"
                />
                <div
                  className={cn(
                    "h-full rounded-2xl border-2 p-5 text-center transition-all duration-200",
                    active
                      ? "border-purple-400/70 bg-gradient-to-br from-purple-600/25 to-fuchsia-600/25 shadow-playoot-md -translate-y-0.5"
                      : "border-white/10 bg-white/5 hover:border-white/25 hover:bg-white/10"
                  )}
                >
                  <div className="text-3xl mb-2">{meta.icon}</div>
                  <div className="font-semibold text-white capitalize">{meta.label}</div>
                  <div className="text-xs text-gray-400 mt-1">{meta.desc}</div>
                </div>
              </label>
            );
          })}
        </div>

        {sourceType === "topic" && (
          <Input
            label="Topic"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="e.g., JavaScript Fundamentals, World War II, Periodic Table"
            required
            helperText="Be specific for better questions."
          />
        )}

        {sourceType === "prompt" && (
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Prompt</label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="e.g., Create a quiz about React hooks with focus on useEffect and useState. Include code snippets in questions."
              rows={4}
              className="glass-input w-full px-4 py-3 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none"
              required
            />
            <p className="text-xs text-gray-500 mt-1">Describe exactly what you want the quiz to cover.</p>
          </div>
        )}

        {sourceType === "pdf" && (
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">PDF File</label>
            <input
              type="file"
              accept=".pdf"
              onChange={(e) => setPdfFile(e.target.files?.[0] || null)}
              className="glass-input w-full px-4 py-3 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-gradient-to-r file:from-purple-600 file:to-fuchsia-600 file:text-white hover:file:from-purple-500 hover:file:to-fuchsia-500"
              required
            />
            {pdfFile && (
              <p className="text-sm text-emerald-400 mt-2 flex items-center gap-2">
                ✅ {pdfFile.name} ({(pdfFile.size / 1024).toFixed(1)} KB)
              </p>
            )}
            <p className="text-xs text-gray-500 mt-1">Maximum 10MB. Text will be extracted for question generation.</p>
          </div>
        )}
      </section>


      {/* Collapsible subsections */}
      <div className="space-y-4">
        <CollapsibleSection
          title="Quiz Setup"
          subtitle="Title, difficulty & length"
          icon="🎯"
          accent="purple"
          defaultOpen
          badge={
            <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-white/10 text-gray-200">
              {questionCount} questions · {difficulty}
            </span>
          }
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <Input
              label="Quiz Title (optional)"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Auto-generated if empty"
            />
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Difficulty</label>
              <select
                value={difficulty}
                onChange={(e) => setDifficulty(e.target.value as typeof difficulty)}
                className="glass-input w-full px-4 py-3 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
              >
                {DIFFICULTY_OPTIONS.map((d) => (
                  <option key={d} value={d} className="bg-gray-900 capitalize">
                    {d}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mt-5">
            <Input
              label="Number of Questions"
              type="number"
              value={questionCount}
              onChange={(e) =>
                setQuestionCount(
                  clampInt(
                    e.target.value,
                    questionCount,
                    MIN_GENERATED_QUESTIONS,
                    MAX_GENERATED_QUESTIONS
                  )
                )
              }
              min={MIN_GENERATED_QUESTIONS}
              max={MAX_GENERATED_QUESTIONS}
              helperText={`${MIN_GENERATED_QUESTIONS}–${MAX_GENERATED_QUESTIONS} questions`}
            />
            <ScrollSelect
              label="Options per Question"
              value={optionCount}
              options={OPTION_COUNTS}
              onChange={setOptionCount}
              min={MIN_OPTION_COUNT}
              max={MAX_OPTION_COUNT}
              helperText="How many answer choices each question shows."
            />
          </div>

          <div className="mt-5">
            <label className="block text-sm font-medium text-gray-300 mb-3">Number of Winners</label>
            <div className="flex flex-wrap gap-3">
              {([1, 3, 5, 10] as const).map((count) => (
                <button
                  key={count}
                  type="button"
                  onClick={() => setWinnersCount(count)}
                  className={cn(
                    "px-4 py-2 rounded-xl text-sm font-medium border-2 transition-all duration-200",
                    winnersCount === count
                      ? "border-transparent bg-gradient-to-r from-purple-600 to-fuchsia-600 text-white shadow-playoot-sm"
                      : "border-white/10 bg-white/5 text-gray-300 hover:border-white/25 hover:bg-white/10"
                  )}
                >
                  Top {count}
                </button>
              ))}
            </div>
            <p className="text-xs text-gray-500 mt-2">
              Number of top teams/players to announce as winners.
            </p>
          </div>
        </CollapsibleSection>

        <CollapsibleSection
          title="Timing"
          subtitle="How long players get per question"
          icon="⏱️"
          accent="cyan"
          badge={
            <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-white/10 text-cyan-200">
              {timeLimit}s
            </span>
          }
        >
          <label className="block text-sm font-medium text-gray-300 mb-3">Time Limit per Question</label>
          <SelectWithCustom
            value={timeLimit}
            onChange={(v) => setTimeLimit(clampInt(v, timeLimit, TIMER_MIN, TIMER_MAX))}
            presets={TIMER_PRESETS}
            unit="sec"
            min={TIMER_MIN}
            max={TIMER_MAX}
          />
          <p className="text-xs text-gray-500 mt-2">
            Allowed range: {TIMER_MIN}–{TIMER_MAX} seconds.
          </p>
        </CollapsibleSection>

        <CollapsibleSection
          title="Marks & Scoring"
          subtitle="Base points awarded per question"
          icon="🏆"
          accent="amber"
          badge={
            <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-white/10 text-amber-200">
              {points} pts
            </span>
          }
        >
          <label className="block text-sm font-medium text-gray-300 mb-3">Base Points per Question</label>
          <SelectWithCustom
            value={points}
            onChange={(v) => setPoints(clampInt(v, points, POINTS_MIN, POINTS_MAX))}
            presets={POINTS_PRESETS}
            unit="pts"
            min={POINTS_MIN}
            max={POINTS_MAX}
          />
        </CollapsibleSection>


        <CollapsibleSection
          title="Question Types"
          subtitle="Mix and match formats"
          icon="🧩"
          accent="pink"
          badge={
            <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-white/10 text-pink-200">
              {questionTypes.length} selected
            </span>
          }
        >
          <div className="flex flex-wrap gap-3">
            {(["multiple_choice", "multiple_answer", "fill_blank", "true_false"] as const).map((type) => {
              const active = questionTypes.includes(type);
              return (
                <button
                  key={type}
                  type="button"
                  onClick={() => toggleQuestionType(type)}
                  className={cn(
                    "px-4 py-2.5 rounded-xl text-sm font-medium border-2 capitalize transition-all duration-200",
                    active
                      ? "border-transparent bg-gradient-to-r from-pink-600 to-purple-600 text-white shadow-pink-500/25 shadow-lg"
                      : "border-white/10 bg-white/5 text-gray-300 hover:border-white/25 hover:bg-white/10"
                  )}
                >
                  {type.replace(/_/g, " ")}
                </button>
              );
            })}
          </div>
          <p className="text-xs text-gray-500 mt-3">
            At least one type must be selected. Questions will be distributed across selected types.
          </p>
        </CollapsibleSection>

        <CollapsibleSection
          title="Advanced"
          subtitle="Extra guidance for the AI"
          icon="🛠️"
          accent="emerald"
        >
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Custom Instructions (optional)
          </label>
          <textarea
            value={customInstructions}
            onChange={(e) => setCustomInstructions(e.target.value)}
            placeholder="e.g., Focus on practical examples, avoid trick questions, include real-world scenarios, make questions accessible to beginners..."
            rows={3}
            className="glass-input w-full px-4 py-3 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none"
          />
          <p className="text-xs text-gray-500 mt-1">Additional guidance for the AI when generating questions.</p>
        </CollapsibleSection>
      </div>

      {/* Generate */}
      <Button
        onClick={handleGenerate}
        variant="rainbow"
        size="xl"
        className="w-full rounded-2xl py-6 text-lg"
        loading={loading}
      >
        {loading ? "Generating..." : "✨ Generate Questions"}
      </Button>
    </div>
  );
}
