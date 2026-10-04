import { Link } from "react-router-dom";
import { Button } from "../components/ui/Button";
import { Card, CardContent } from "../components/ui/Card";
import { Logo } from "../components/Logo";

export function HomePage() {
  return (
    <div className="max-w-5xl mx-auto space-y-12 sm:space-y-16 py-4 sm:py-6">
      {/* Hero */}
      <section className="text-center space-y-8">
        <div className="flex justify-center">
          <span className="glass-card inline-flex flex-wrap justify-center items-center gap-2 sm:gap-3 px-4 sm:px-5 py-2.5 sm:py-3 rounded-full text-xs sm:text-sm font-medium text-gray-200 max-w-full">
            <Logo size={26} showWordmark={false} />
            <span className="bg-gradient-to-r from-purple-300 via-pink-300 to-cyan-300 bg-clip-text text-transparent font-semibold tracking-wide">
              PLAYOOT IN EVERYWHERE
            </span>
            <span className="text-[10px] uppercase tracking-widest text-purple-300/80 border border-purple-400/30 rounded-full px-2 py-0.5">
              Beta
            </span>
          </span>
        </div>

        <h1 className="text-4xl sm:text-5xl md:text-7xl font-bold tracking-tight leading-[1.05]">
          <span className="gradient-text">Create. Host. Play.</span>
        </h1>

        <p className="text-base sm:text-lg md:text-2xl text-gray-300 max-w-2xl mx-auto">
          Build engaging quizzes with AI, host live multiplayer games, and compete with
          friends or colleagues in real-time.
        </p>

        {/* Primary actions */}
        <div className="flex flex-col md:flex-row items-stretch justify-center gap-4 sm:gap-6 pt-2">
          <Link to="/register">
            <Button
              size="xl"
              variant="rainbow"
              className="w-full sm:w-auto sm:min-w-[300px] py-5 sm:py-6 rounded-2xl"
              leftIcon={<span className="text-3xl">✨</span>}
            >
              <span className="flex flex-col items-start text-left">
                <span className="font-bold text-lg">Create Quiz</span>
                <span className="text-sm font-normal opacity-90">
                  Sign up to build &amp; host games
                </span>
              </span>
            </Button>
          </Link>

          <Link to="/join">
            <div className="rainbow-border h-full rounded-2xl">
              <Button
                size="xl"
                variant="outline"
                className="w-full sm:w-auto sm:min-w-[300px] py-5 sm:py-6 h-full rounded-2xl border-2 border-purple-500/40 bg-gray-900/40 hover:border-purple-400 hover:bg-purple-500/10"
                leftIcon={<span className="text-3xl">🎮</span>}
              >
                <span className="flex flex-col items-start text-left">
                  <span className="font-bold text-lg text-white">Join Quiz</span>
                  <span className="text-sm font-normal text-gray-400">
                    Enter PIN and play instantly
                  </span>
                </span>
              </Button>
            </div>
          </Link>
        </div>
      </section>

      {/* Features */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <FeatureCard
          icon="🤖"
          accent="from-purple-500/30 to-fuchsia-500/30"
          title="AI-Generated Questions"
          description="Create quizzes from topics, PDFs, or custom prompts using Groq's lightning-fast LLMs."
        />
        <FeatureCard
          icon="👥"
          accent="from-cyan-500/30 to-blue-500/30"
          title="Team & Individual Modes"
          description="Play solo or in teams of up to 4. Real-time scoring, leaderboards, and live updates."
        />
        <FeatureCard
          icon="⚡"
          accent="from-pink-500/30 to-orange-500/30"
          title="Server-Authoritative"
          description="No cheating possible. The server owns the timer, validates answers, and calculates scores."
        />
      </section>

      {/* How it works */}
      <section className="border-t border-white/10 pt-12">
        <h2 className="text-2xl font-bold mb-8 text-center">
          <span className="bg-gradient-to-r from-purple-300 to-cyan-300 bg-clip-text text-transparent">
            How It Works
          </span>
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Step number={1} title="Create Quiz" description="Build manually or generate with AI from topics, PDFs, or prompts." />
          <Step number={2} title="Start Game" description="Pick a mode, get a 6-digit PIN, and share it with players." />
          <Step number={3} title="Players Join" description="Players enter the PIN and nickname on any device — no account needed." />
          <Step number={4} title="Play Live" description="Real-time questions, instant scoring, live leaderboards." />
        </div>
      </section>
    </div>
  );
}

function FeatureCard({
  icon,
  title,
  description,
  accent,
}: {
  icon: string;
  title: string;
  description: string;
  accent: string;
}) {
  return (
    <Card variant="glass" interactive className="h-full">
      <CardContent className="py-8 text-center space-y-4">
        <div
          className={`mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br ${accent} text-3xl shadow-inner`}
        >
          {icon}
        </div>
        <h3 className="text-lg font-semibold text-white">{title}</h3>
        <p className="text-sm text-gray-400">{description}</p>
      </CardContent>
    </Card>
  );
}

function Step({ number, title, description }: { number: number; title: string; description: string }) {
  return (
    <div className="relative pl-12 pb-8 before:absolute before:left-0 before:top-0 before:w-1 before:h-full before:bg-gradient-to-b before:from-purple-500/50 before:to-transparent last:before:hidden">
      <div className="relative flex items-start gap-3">
        <div className="w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm flex-shrink-0 bg-gradient-to-br from-purple-500 to-fuchsia-600 text-white shadow-playoot-sm">
          {number}
        </div>
        <div>
          <h4 className="font-semibold text-gray-100">{title}</h4>
          <p className="text-sm text-gray-500">{description}</p>
        </div>
      </div>
    </div>
  );
}
