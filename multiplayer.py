"""
CYBER SNAKE 2077 - Real-Time Multiplayer Game Engine (High-Performance Edition)
Authoritative server-side game rooms, sub-millisecond input queues,
concurrent WebSocket broadcasting, and low-latency physics loops.
"""

import asyncio
from collections import deque
import json
import math
import random
import time
from typing import Dict, List, Optional, Set, Tuple
from fastapi import WebSocket


GRID_WIDTH = 32
GRID_HEIGHT = 32
TICK_INTERVAL = 0.070  # ~14.3 updates/sec (optimized for snappy, low-latency turns)
INVULNERABLE_TICKS = 26  # ~1.8 seconds spawn protection
FOOD_TARGET_COUNT = 10
GOLDEN_FOOD_INTERVAL = 14.0  # seconds between golden food spawns
GOLDEN_FOOD_LIFESPAN = 8.0  # seconds golden food stays active

NEON_COLORS = [
    "#00ff88",  # Neon Green
    "#00e5ff",  # Cyber Cyan
    "#ff0055",  # Laser Pink
    "#ffd700",  # Solar Gold
    "#b026ff",  # Plasma Purple
    "#ff6600",  # Blaze Orange
    "#00ffff",  # Electric Aqua
    "#ff3399",  # Neon Rose
]


class Player:
    def __init__(self, player_id: str, websocket: WebSocket, name: str = "Runner", color: str = "#00ff88"):
        self.id = player_id
        self.ws = websocket
        self.name = name[:16].strip() or "Runner"
        self.color = color if color in NEON_COLORS else random.choice(NEON_COLORS)
        self.snake: List[Tuple[int, int]] = []
        self.dir: Tuple[int, int] = (1, 0)
        self.input_queue: deque = deque(maxlen=2)  # Buffer up to 2 rapid turn inputs
        self.score: int = 0
        self.kills: int = 0
        self.deaths: int = 0
        self.is_alive: bool = False
        self.invulnerable_ticks: int = 0
        self.grow_pending: int = 0
        self.recent_message: Optional[str] = None
        self.message_expires_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "body": self.snake,
            "dir": list(self.dir),
            "score": self.score,
            "kills": self.kills,
            "deaths": self.deaths,
            "isAlive": self.is_alive,
            "invulnerable": self.invulnerable_ticks > 0,
            "chat": self.recent_message if time.time() < self.message_expires_at else None,
        }


class Food:
    def __init__(self, food_id: int, x: int, y: int, food_type: str = "normal", points: int = 10, grow: int = 1, lifespan: Optional[float] = None):
        self.id = food_id
        self.x = x
        self.y = y
        self.type = food_type  # 'normal', 'golden', 'corpse'
        self.points = points
        self.grow = grow
        self.expires_at = time.time() + lifespan if lifespan else None

    def to_dict(self) -> dict:
        remaining = max(0.0, round(self.expires_at - time.time(), 1)) if self.expires_at else None
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "type": self.type,
            "points": self.points,
            "expires": remaining,
        }


class GameRoom:
    def __init__(self, room_id: str):
        self.room_id = room_id
        self.width = GRID_WIDTH
        self.height = GRID_HEIGHT
        self.wall_mode = "wrap"  # 'wrap' or 'deadly'
        self.players: Dict[str, Player] = {}
        self.foods: Dict[int, Food] = {}
        self.next_food_id = 1
        self.next_event_id = 1
        self.events: List[dict] = []
        self.loop_task: Optional[asyncio.Task] = None
        self.last_golden_spawn = time.time()
        self.is_running = False

    def add_event(self, text: str, event_type: str = "info"):
        evt = {
            "id": self.next_event_id,
            "text": text,
            "type": event_type,
            "time": time.time(),
        }
        self.next_event_id += 1
        self.events.append(evt)
        if len(self.events) > 20:
            self.events.pop(0)

    def spawn_player_snake(self, player: Player):
        occupied_cells: Set[Tuple[int, int]] = set()
        for p in self.players.values():
            if p.is_alive:
                occupied_cells.update(p.snake)

        # Find safe clear area for spawning
        spawn_x, spawn_y = random.randint(4, self.width - 5), random.randint(4, self.height - 5)
        for _ in range(40):
            test_x, test_y = random.randint(4, self.width - 5), random.randint(4, self.height - 5)
            safe = True
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    if (test_x + dx, test_y + dy) in occupied_cells:
                        safe = False
                        break
                if not safe:
                    break
            if safe:
                spawn_x, spawn_y = test_x, test_y
                break

        directions = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        d = random.choice(directions)

        player.snake = [
            (spawn_x, spawn_y),
            (spawn_x - d[0], spawn_y - d[1]),
            (spawn_x - d[0] * 2, spawn_y - d[1] * 2),
        ]
        player.dir = d
        player.input_queue.clear()
        player.is_alive = True
        player.invulnerable_ticks = INVULNERABLE_TICKS
        player.grow_pending = 0

    def add_player(self, player_id: str, ws: WebSocket, name: str, color: str) -> Player:
        player = Player(player_id, ws, name, color)
        self.players[player_id] = player
        self.spawn_player_snake(player)
        self.add_event(f"⚡ {player.name} joined the arena", "join")
        self.ensure_loop_started()
        return player

    def remove_player(self, player_id: str):
        player = self.players.pop(player_id, None)
        if player:
            if player.is_alive:
                self.turn_body_to_food(player.snake)
            self.add_event(f"👋 {player.name} left the arena", "leave")

        if not self.players and self.loop_task:
            self.is_running = False
            self.loop_task.cancel()
            self.loop_task = None

    def turn_body_to_food(self, body: List[Tuple[int, int]]):
        for idx, (bx, by) in enumerate(body):
            if idx % 2 == 0:
                fid = self.next_food_id
                self.next_food_id += 1
                self.foods[fid] = Food(fid, bx, by, food_type="corpse", points=15, grow=1, lifespan=16.0)

    def handle_input(self, player_id: str, direction_str: str):
        player = self.players.get(player_id)
        if not player or not player.is_alive:
            return

        dir_map = {
            "UP": (0, -1),
            "DOWN": (0, 1),
            "LEFT": (-1, 0),
            "RIGHT": (1, 0),
        }
        new_d = dir_map.get(direction_str.upper())
        if not new_d:
            return

        # Compare with last queued turn or current direction
        ref_d = player.input_queue[-1] if player.input_queue else player.dir

        # Disallow 180° immediate self-reversal
        if (new_d[0] != 0 and new_d[0] == -ref_d[0]) or (new_d[1] != 0 and new_d[1] == -ref_d[1]):
            return

        # Do not queue duplicate identical direction
        if new_d == ref_d:
            return

        player.input_queue.append(new_d)

    def respawn_player(self, player_id: str):
        player = self.players.get(player_id)
        if player and not player.is_alive:
            self.spawn_player_snake(player)
            self.add_event(f"✨ {player.name} respawned!", "respawn")

    def handle_chat(self, player_id: str, msg: str):
        player = self.players.get(player_id)
        if not player:
            return
        clean_msg = msg[:32].strip()
        if not clean_msg:
            return
        player.recent_message = clean_msg
        player.message_expires_at = time.time() + 4.0
        self.add_event(f"💬 {player.name}: {clean_msg}", "chat")

    def ensure_loop_started(self):
        if not self.is_running or not self.loop_task or self.loop_task.done():
            self.is_running = True
            self.loop_task = asyncio.create_task(self._run_loop())

    async def _run_loop(self):
        try:
            while self.is_running and self.players:
                start_time = asyncio.get_event_loop().time()
                await self.tick()
                elapsed = asyncio.get_event_loop().time() - start_time
                await asyncio.sleep(max(0.002, TICK_INTERVAL - elapsed))
        except asyncio.CancelledError:
            pass
        finally:
            self.is_running = False

    def maintain_foods(self):
        now = time.time()
        # Clean expired foods
        expired = [fid for fid, f in self.foods.items() if f.expires_at and f.expires_at <= now]
        for fid in expired:
            del self.foods[fid]

        occupied: Set[Tuple[int, int]] = set()
        for p in self.players.values():
            if p.is_alive:
                occupied.update(p.snake)
        for f in self.foods.values():
            occupied.add((f.x, f.y))

        # Maintain regular foods
        normal_foods = sum(1 for f in self.foods.values() if f.type == "normal")
        while normal_foods < FOOD_TARGET_COUNT:
            fx, fy = random.randint(1, self.width - 2), random.randint(1, self.height - 2)
            if (fx, fy) not in occupied:
                fid = self.next_food_id
                self.next_food_id += 1
                self.foods[fid] = Food(fid, fx, fy, food_type="normal", points=10, grow=1)
                occupied.add((fx, fy))
                normal_foods += 1

        # Spawn periodic golden bonus food
        golden_count = sum(1 for f in self.foods.values() if f.type == "golden")
        if golden_count == 0 and (now - self.last_golden_spawn) > GOLDEN_FOOD_INTERVAL:
            for _ in range(20):
                gx, gy = random.randint(2, self.width - 3), random.randint(2, self.height - 3)
                if (gx, gy) not in occupied:
                    fid = self.next_food_id
                    self.next_food_id += 1
                    self.foods[fid] = Food(fid, gx, gy, food_type="golden", points=50, grow=2, lifespan=GOLDEN_FOOD_LIFESPAN)
                    self.last_golden_spawn = now
                    self.add_event("⭐ A Golden Bonus Orb has spawned!", "bonus")
                    break

    async def tick(self):
        alive_players = [p for p in self.players.values() if p.is_alive]
        new_heads: Dict[str, Tuple[int, int]] = {}

        # 1. Dequeue queued player inputs and calculate candidate new heads
        for p in alive_players:
            if p.input_queue:
                p.dir = p.input_queue.popleft()

            hx = p.snake[0][0] + p.dir[0]
            hy = p.snake[0][1] + p.dir[1]

            if self.wall_mode == "wrap":
                hx %= self.width
                hy %= self.height
            else:
                if hx < 0 or hx >= self.width or hy < 0 or hy >= self.height:
                    new_heads[p.id] = (hx, hy)
                    continue

            new_heads[p.id] = (hx, hy)

        # 2. Collision Detection
        dead_players: Set[str] = set()
        killer_map: Dict[str, str] = {}

        # A. Check Wall Collisions
        if self.wall_mode == "deadly":
            for p in alive_players:
                nh = new_heads.get(p.id)
                if nh and (nh[0] < 0 or nh[0] >= self.width or nh[1] < 0 or nh[1] >= self.height):
                    dead_players.add(p.id)
                    self.add_event(f"💥 {p.name} crashed into the electric wall!", "death")

        # B. Check Self Collisions
        for p in alive_players:
            if p.id in dead_players:
                continue
            nh = new_heads.get(p.id)
            if not nh:
                continue
            body_to_check = p.snake[:-1] if p.grow_pending <= 0 else p.snake
            if nh in body_to_check:
                dead_players.add(p.id)
                self.add_event(f"💥 {p.name} ran into their own tail!", "death")

        # C. Check Other Snake Collisions
        for p in alive_players:
            if p.id in dead_players:
                continue
            nh = new_heads.get(p.id)
            if not nh or p.invulnerable_ticks > 0:
                continue

            for other in alive_players:
                if other.id == p.id:
                    continue
                other_body_to_check = other.snake[:-1] if other.grow_pending <= 0 else other.snake
                if nh in other_body_to_check:
                    dead_players.add(p.id)
                    killer_map[p.id] = other.id
                    self.add_event(f"⚔️ {other.name} cut off {p.name}!", "kill")
                    break

        # D. Head-to-Head Collisions
        for i in range(len(alive_players)):
            p1 = alive_players[i]
            if p1.id in dead_players:
                continue
            nh1 = new_heads.get(p1.id)
            if not nh1:
                continue

            for j in range(i + 1, len(alive_players)):
                p2 = alive_players[j]
                if p2.id in dead_players:
                    continue
                nh2 = new_heads.get(p2.id)
                if not nh2:
                    continue

                if nh1 == nh2:
                    if p1.invulnerable_ticks > 0 and p2.invulnerable_ticks == 0:
                        dead_players.add(p2.id)
                        killer_map[p2.id] = p1.id
                        self.add_event(f"⚔️ {p1.name} crushed {p2.name} head-on!", "kill")
                    elif p2.invulnerable_ticks > 0 and p1.invulnerable_ticks == 0:
                        dead_players.add(p1.id)
                        killer_map[p1.id] = p2.id
                        self.add_event(f"⚔️ {p2.name} crushed {p1.name} head-on!", "kill")
                    else:
                        dead_players.add(p1.id)
                        dead_players.add(p2.id)
                        self.add_event(f"💥 Head-on collision between {p1.name} and {p2.name}!", "death")

        # 3. Handle Killers & Deaths
        for victim_id in dead_players:
            victim = self.players.get(victim_id)
            if victim:
                victim.is_alive = False
                victim.deaths += 1
                victim.input_queue.clear()
                self.turn_body_to_food(victim.snake)

                killer_id = killer_map.get(victim_id)
                if killer_id:
                    killer = self.players.get(killer_id)
                    if killer:
                        killer.kills += 1
                        killer.score += 50

        # 4. Move Surviving Snakes & Handle Food Consumption
        eaten_foods: List[int] = []
        for p in alive_players:
            if p.id in dead_players:
                continue
            nh = new_heads.get(p.id)
            if not nh:
                continue

            p.snake.insert(0, nh)

            food_eaten = None
            for fid, f in self.foods.items():
                if f.x == nh[0] and f.y == nh[1]:
                    food_eaten = f
                    eaten_foods.append(fid)
                    break

            if food_eaten:
                p.score += food_eaten.points
                p.grow_pending += food_eaten.grow
                if food_eaten.type == "golden":
                    self.add_event(f"⭐ {p.name} collected a Golden Orb (+50)!", "bonus")

            if p.grow_pending > 0:
                p.grow_pending -= 1
            else:
                p.snake.pop()

            if p.invulnerable_ticks > 0:
                p.invulnerable_ticks -= 1

        for fid in eaten_foods:
            self.foods.pop(fid, None)

        self.maintain_foods()
        await self.broadcast_state()

    def get_snapshot(self) -> dict:
        player_list = [p.to_dict() for p in self.players.values()]
        leaderboard = sorted(
            [
                {
                    "id": p.id,
                    "name": p.name,
                    "color": p.color,
                    "score": p.score,
                    "kills": p.kills,
                    "isAlive": p.is_alive,
                }
                for p in self.players.values()
            ],
            key=lambda x: (x["score"], x["kills"]),
            reverse=True,
        )

        return {
            "type": "state",
            "serverTime": round(time.time() * 1000),
            "tickDuration": int(TICK_INTERVAL * 1000),
            "room": self.room_id,
            "grid": {"width": self.width, "height": self.height},
            "wallMode": self.wall_mode,
            "players": player_list,
            "foods": [f.to_dict() for f in self.foods.values()],
            "events": self.events[-5:],
            "leaderboard": leaderboard,
        }

    async def broadcast_state(self):
        if not self.players:
            return

        payload = json.dumps(self.get_snapshot(), separators=(",", ":"))
        disconnected = []

        async def _send(pid: str, player: Player):
            try:
                await player.ws.send_text(payload)
            except Exception:
                disconnected.append(pid)

        # Broadcast in parallel to eliminate sequential network blocking across Wi-Fi
        await asyncio.gather(*[_send(pid, p) for pid, p in list(self.players.items())])

        for pid in disconnected:
            self.remove_player(pid)


class RoomManager:
    def __init__(self):
        self.rooms: Dict[str, GameRoom] = {}

    def get_or_create_room(self, room_id: str) -> GameRoom:
        clean_id = room_id.strip().lower() or "arena"
        if clean_id not in self.rooms:
            self.rooms[clean_id] = GameRoom(clean_id)
        return self.rooms[clean_id]

    def remove_empty_rooms(self):
        empty = [rid for rid, r in self.rooms.items() if not r.players and rid != "arena"]
        for rid in empty:
            del self.rooms[rid]


room_manager = RoomManager()
