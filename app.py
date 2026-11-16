import asyncio
import socket
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from multiplayer import NEON_COLORS, room_manager

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DB_PATH = BASE_DIR / "snake_scores.db"

app = FastAPI(title="Retro Neon Snake Game - Multiplayer Edition", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_lan_ip() -> str:
    """Retrieve the active local LAN IPv4 address for network multiplayer."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leaderboard (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name TEXT NOT NULL,
                score INTEGER NOT NULL,
                difficulty TEXT NOT NULL,
                snake_length INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur = conn.execute("SELECT COUNT(*) as cnt FROM leaderboard")
        if cur.fetchone()["cnt"] == 0:
            sample_scores = [
                ("NeonRider", 320, "normal", 35),
                ("PixelMaster", 250, "hard", 28),
                ("CyberViper", 180, "normal", 21),
                ("RetroKing", 140, "easy", 17),
                ("ByteNibbler", 90, "normal", 12),
            ]
            conn.executemany(
                """
                INSERT INTO leaderboard (player_name, score, difficulty, snake_length)
                VALUES (?, ?, ?, ?)
                """,
                sample_scores,
            )
            conn.commit()


init_db()


class ScoreSubmission(BaseModel):
    player_name: str = Field(..., min_length=1, max_length=20)
    score: int = Field(..., ge=0, le=100000)
    difficulty: str = Field(default="normal", max_length=10)
    snake_length: int = Field(..., ge=1, le=5000)


@app.get("/")
def serve_home():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Frontend file not found")
    return FileResponse(
        index_file,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/api/network-info")
def get_network_info():
    lan_ip = get_lan_ip()
    port = 8000
    active_rooms = len(room_manager.rooms)
    active_players = sum(len(r.players) for r in room_manager.rooms.values())
    return {
        "local_ip": lan_ip,
        "port": port,
        "local_url": f"http://{lan_ip}:{port}",
        "active_rooms": active_rooms,
        "active_players": active_players,
        "neon_colors": NEON_COLORS,
    }


@app.get("/api/leaderboard")
def get_leaderboard(limit: int = 10):
    clamped_limit = max(1, min(limit, 50))
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT player_name, score, difficulty, snake_length, created_at
            FROM leaderboard
            ORDER BY score DESC, snake_length DESC, id ASC
            LIMIT ?
            """,
            (clamped_limit,),
        ).fetchall()
        return [
            {
                "rank": idx + 1,
                "player_name": r["player_name"],
                "score": r["score"],
                "difficulty": r["difficulty"],
                "snake_length": r["snake_length"],
                "created_at": r["created_at"],
            }
            for idx, r in enumerate(rows)
        ]


@app.post("/api/score")
def submit_score(submission: ScoreSubmission):
    clean_name = submission.player_name.strip()
    if not clean_name:
        clean_name = "Anonymous"

    valid_difficulties = {"easy", "normal", "hard", "extreme"}
    diff = submission.difficulty.lower()
    if diff not in valid_difficulties:
        diff = "normal"

    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO leaderboard (player_name, score, difficulty, snake_length)
            VALUES (?, ?, ?, ?)
            """,
            (clean_name, submission.score, diff, submission.snake_length),
        )
        new_id = cur.lastrowid
        conn.commit()

        rank_cur = conn.execute(
            """
            SELECT COUNT(*) + 1 as rank
            FROM leaderboard
            WHERE score > ? OR (score = ? AND id < ?)
            """,
            (submission.score, submission.score, new_id),
        )
        rank = rank_cur.fetchone()["rank"]

    return {
        "success": True,
        "rank": rank,
        "is_top_10": rank <= 10,
        "message": f"Score saved! You ranked #{rank} on the leaderboard.",
    }


@app.get("/api/stats")
def get_stats():
    with get_db() as conn:
        stats = conn.execute(
            """
            SELECT 
                COUNT(*) as total_games,
                COALESCE(MAX(score), 0) as high_score,
                COALESCE(ROUND(AVG(score), 1), 0) as average_score
            FROM leaderboard
            """
        ).fetchone()

        return {
            "total_games": stats["total_games"],
            "high_score": stats["high_score"],
            "average_score": stats["average_score"],
        }


# ============================================================================
# REAL-TIME MULTIPLAYER WEBSOCKET ENDPOINT
# ============================================================================

@app.websocket("/ws/game/{room_id}")
async def websocket_game_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()
    # Disable Nagle's algorithm to eliminate network buffering latency
    try:
        raw_sock = websocket.scope.get("transport", None)
        if raw_sock and hasattr(raw_sock, "get_extra_info"):
            sock = raw_sock.get_extra_info("socket")
            if sock:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception:
        pass

    player_id = str(uuid.uuid4())[:8]
    room = room_manager.get_or_create_room(room_id)
    player = None

    try:
        # First message expected is the join message with pilot callsign and color
        init_data = await websocket.receive_json()
        if init_data.get("type") == "join":
            name = init_data.get("name", "Runner")
            color = init_data.get("color", "#00ff88")
            player = room.add_player(player_id, websocket, name, color)
        else:
            player = room.add_player(player_id, websocket, "Runner", "#00ff88")

        # Send welcome payload with confirmed ID and room config
        await websocket.send_json({
            "type": "welcome",
            "playerId": player_id,
            "room": room.room_id,
            "grid": {"width": room.width, "height": room.height},
            "wallMode": room.wall_mode,
        })

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "input":
                direction = data.get("dir")
                if direction:
                    room.handle_input(player_id, direction)

            elif msg_type == "respawn":
                room.respawn_player(player_id)

            elif msg_type == "chat":
                msg = data.get("message", "")
                room.handle_chat(player_id, msg)

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong", "t": data.get("t")})

            elif msg_type == "set_wall_mode":
                new_mode = data.get("mode")
                if new_mode in ("wrap", "deadly"):
                    room.wall_mode = new_mode
                    room.add_event(f"⚙️ Wall mode changed to {new_mode.upper()}", "info")

    except WebSocketDisconnect:
        room.remove_player(player_id)
    except Exception:
        room.remove_player(player_id)


# Mount static assets directory
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    lan_ip = get_lan_ip()
    print("=" * 64)
    print("   CYBER SNAKE 2077 - MULTIPLAYER SERVER LAUNCHED")
    print(f"   Local Browser:   http://localhost:8000")
    print(f"   Friends Link:    http://{lan_ip}:8000")
    print("=" * 64)
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
