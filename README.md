# PLAYOOT IN EVERYWHERE - Multiplayer Quiz Platform

A Kahoot-inspired multiplayer quiz platform with AI-powered question generation, real-time gameplay, and team/individual modes.

## Features

- 🤖 **AI Question Generation** - Create quizzes from topics, PDFs, or custom prompts using Groq
- 👤 **Individual Mode** - Classic head-to-head competition
- 👥 **Team Mode** - Teams of up to 4 players with aggregated scoring
- ⚡ **Real-time Gameplay** - WebSocket-based live questions, answers, and leaderboards
- 🔐 **Secure** - Server-authoritative game engine, JWT authentication
- 📱 **Responsive** - Works on desktop and mobile

## Architecture

```
Kahoot Game/
├── backend/           # FastAPI + WebSocket server
│   ├── app/
│   │   ├── api/       # REST endpoints (auth, quizzes, games)
│   │   ├── game/      # Game engine, WebSocket handler, scoring
│   │   ├── ai/        # Groq-based question generation
│   │   ├── models/    # SQLAlchemy models
│   │   └── services/  # Business logic
│   └── alembic/       # Database migrations
├── frontend/          # React + Vite + TypeScript + Tailwind
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── services/
│   │   └── types/
└── docker-compose.yml
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Groq API key (for AI generation) - get one at https://console.groq.com/

### Development

1. **Clone and configure**
   ```bash
   cd "Kahoot Game"
   cp backend/.env.example backend/.env
   cp frontend/.env.example frontend/.env
   # Edit backend/.env and add your GROQ_API_KEY
   ```

2. **Start with Docker Compose**
   ```bash
   docker-compose up --build
   ```

3. **Access**
   - Frontend: http://localhost:5173
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

### Manual Setup (without Docker)

#### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your settings
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

#### Frontend
```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

## Game Flow

### Individual Mode
```
1. Host creates/selects quiz → 2. Host starts game → 3. Players join via PIN
4. Host begins → 5. Questions broadcast → 6. Players answer
7. Server validates → 8. Scores update → 9. Leaderboard
10. Next question → ... → Final Results
```

### Team Mode
```
1. Host creates game in "team" mode
2. Players join and create/join teams (max 4/team)
3. Host starts game
4. Players answer individually
5. Team score = sum of member scores
6. Team leaderboard displayed
```

## API Endpoints

### Authentication
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login
- `GET /api/auth/me` - Get current user

### Quizzes
- `GET /api/quizzes` - List user's quizzes
- `POST /api/quizzes` - Create quiz manually
- `GET /api/quizzes/{id}` - Get quiz details
- `PUT /api/quizzes/{id}` - Update quiz
- `DELETE /api/quizzes/{id}` - Delete quiz
- `POST /api/quizzes/generate` - AI generate from topic/prompt
- `POST /api/quizzes/generate/pdf` - AI generate from PDF

### Games
- `POST /api/games` - Create game (host only)
- `GET /api/games/{pin}` - Lookup game by PIN
- `GET /api/games/{pin}/lobby` - Get lobby state
- `POST /api/games/{pin}/join` - Join as player
- `POST /api/games/{pin}/teams` - Create team
- `POST /api/games/{pin}/teams/join` - Join team
- `GET /api/games/{pin}/results` - Get game results

### WebSocket
- `WS /ws/game/{pin}?player_token=...` - Player connection
- `WS /ws/game/{pin}?token=...` - Host connection

## WebSocket Events

### Server → Client
- `CONNECTED` - Connection established
- `STATE_SYNC` - Full game state snapshot
- `PLAYER_JOINED/PLAYER_LEFT/PLAYER_UPDATED` - Lobby updates
- `TEAM_CREATED/TEAM_JOINED/TEAM_LEFT/TEAM_UPDATED` - Team updates
- `GAME_STARTED` - Game began
- `QUESTION_STARTED` - New question (no correct answer!)
- `ANSWER_SUBMITTED` - Player's answer accepted
- `PLAYER_ANSWERED` - Someone answered (count only)
- `QUESTION_ENDED` - Question closed, reveal + leaderboard
- `LEADERBOARD_UPDATED` - Scores updated
- `NEXT_QUESTION` - Advancing to next question
- `GAME_FINISHED/GAME_CANCELLED` - Game ended
- `GAME_ERROR` - Error with code/message

### Client → Server
- `START_GAME` - Host starts game
- `NEXT_QUESTION` - Host advances
- `END_QUESTION` - Host ends question early
- `END_GAME` - Host ends game
- `CANCEL_GAME` - Host cancels
- `SUBMIT_ANSWER` - Player submits answer
- `REQUEST_STATE` - Request full sync
- `PING` - Heartbeat

## Game State Machine

```
LOBBY → QUESTION_ACTIVE → QUESTION_REVEAL → LEADERBOARD
  ↑                        ↓                    ↓
  └────────────────────────┴────────────────────┘
                                    ↓
                              FINISHED/CANCELLED
```

## Scoring

- **Base points**: 1000 per question (configurable)
- **Speed bonus**: Linear decay from 100% to 50% based on response time
- **Wrong answer**: 0 points
- **Team score**: Sum of all member scores
- **History preserved**: Answer scores stored at submission time

## Security

- JWT tokens for authentication (HS256)
- Player tokens for game rejoining
- Server-authoritative: clients never see correct answers during questions
- Input validation on all endpoints
- CORS configured for frontend origin

## Database Schema

- **users** - Authentication
- **quizzes** - Quiz metadata
- **questions** - Questions with options/correct answer
- **game_sessions** - Active/completed games
- **players** - Players in a game
- **teams** - Teams in a game
- **answers** - Submitted answers with scores

## Environment Variables

### Backend (.env)
| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | Database connection string | `sqlite+aiosqlite:///./quizhost.db` |
| `SECRET_KEY` | JWT signing key | **Required for production** |
| `GROQ_API_KEY` | Groq API key | Required for AI |
| `GROQ_MODEL` | Model to use | `llama-3.3-70b-versatile` |
| `AI_ENABLED` | Enable AI features | `true` |
| `CORS_ORIGINS` | Allowed origins | `http://localhost:5173,...` |

### Frontend (.env)
| Variable | Description |
|----------|-------------|
| `VITE_API_URL` | Backend API base URL |
| `VITE_WS_URL` | WebSocket base URL |

## Testing the Game

### Individual Mode Test
1. Register/login at http://localhost:5173
2. Create a quiz (manual or AI-generated)
3. Click "Host" on the quiz → Note the 6-digit PIN
4. Open 2+ incognito tabs → Go to `/join` → Enter PIN + nicknames
5. Back on host tab → Click "Start Game"
6. Answer questions in player tabs
7. Verify leaderboard updates in real-time

### Team Mode Test
1. Create game with "Team Mode" selected
2. Players join → Create teams (max 4 per team)
3. Players join teams
4. Start game → Answer questions
5. Verify team scores = sum of members

## Known Limitations

- No persistent game history UI (results only available via API)
- PDF text extraction limited to text-based PDFs (not scanned images)
- No question timer sound effects
- No spectator mode
- Single-process WebSocket (doesn't scale horizontally without Redis)

## Next Development Phase

1. **Horizontal scaling** - Add Redis for multi-instance WebSocket support
2. **Game history** - Persistent results page with replay
3. **Question types** - Multiple choice, true/false, ordering
4. **Media support** - Images in questions
5. **Themes** - Customizable game appearance
6. **Tournaments** - Multi-game series with cumulative scoring
7. **Admin panel** - User management, analytics

## License

MIT