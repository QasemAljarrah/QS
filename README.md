# 🐍 Cyber Snake 2077 - Real-Time Multiplayer & Solo Arcade

A cyberpunk-themed arcade Snake Game built with **FastAPI** (Python WebSocket + REST backend) and **HTML5 Canvas / Vanilla JavaScript / Web Audio API** on the frontend.

Now featuring **Real-Time Online & Local Network Multiplayer**! You and your friends can access the exact same link from phones, tablets, laptops, and PCs to slither and battle in the same arena simultaneously.

---

## 🌐 Real-Time Multiplayer Features

- **⚡ Authoritative WebSocket Server:**
  - Real-time multiplayer synchronization running authoritative server-side physics ticks (~12 updates/sec).
  - Smooth multi-snake rendering on a 32x32 cyber arena.
- **⚔️ Arena Combat Rules (Slither / Tron Style):**
  - Cut off opponent snakes! When another snake's head hits your body, they are eliminated and you earn +1 Kill and +50 bonus points.
  - Exploding corpse energy pellets: Destroyed snakes burst into energy orbs that you can devour to grow quickly.
  - Head-on collisions trigger double elimination.
  - 2-second temporary invulnerability shield upon spawning/respawning.
- **🎨 Custom Neon Color Skins & Pilot Callsigns:**
  - Choose from 8 glowing neon skins (*Neon Green, Cyber Cyan, Laser Pink, Solar Gold, Plasma Purple, Blaze Orange, Electric Aqua, Neon Rose*).
  - Floating player callsigns and directional eyes on each snake head.
- **👑 Live In-Game Leaderboard & Kill Feed:**
  - Real-time scoreboard showing rank, score, kills, and live/eliminated status.
  - Dynamic scrolling battle feed showing kills, golden orb collections, and player joins.
- **💬 Quick Taunts & Live Chat:**
  - Instant emote buttons (`🏆 GG!`, `😎 Too fast!`, `⚡ Watch out!`, `💥 OOF!`, `🐍 Nice try!`).
  - Floating speech bubbles render directly above your snake head in real-time.
- **📋 1-Click Friend Sharing:**
  - Automatic local network IP detection.
  - Built-in "COPY INVITE LINK" button to immediately share with friends.
  - Support for custom private rooms via `?room=code`.
- **🕹️ Solo Arcade Mode Included:**
  - Switch between Multiplayer Arena and Solo Arcade anytime with the header toggle.
  - Persistent SQLite database leaderboard with Hall of Fame.

---

## 🚀 How to Play with Friends

### 1. Launch the Server
Double-click `run.bat` in this folder, or run:
```powershell
python app.py
```
The server will bind to `0.0.0.0:8000` (listening on all network interfaces) and automatically detect your Wi-Fi IP address.

### 2. Connect Your Own Browser
Open on your PC:
- **[http://localhost:8000](http://localhost:8000)** (or your local IP: `http://192.168.1.134:8000`)

### 3. Share with Friends

#### Method A: Same Wi-Fi / Local Network (Zero Setup)
Send your friends on the same Wi-Fi or mobile hotspot this link:
```
http://192.168.1.134:8000
```
*(Or click the green **"📋 COPY INVITE LINK"** button right inside the game header!)*
Any friend opening that link on their phone, iPad, or computer will instantly join your battle arena!

#### Method B: Over the Internet (Friends in Other Houses)
If your friends are at their own homes, you can share a free online link using any of these 1-command tools in a new terminal window:

- **Cloudflare Tunnel (Free, No Account Needed):**
  ```powershell
  cloudflared tunnel --url http://localhost:8000
  ```
  *Copy the generated `https://...trycloudflare.com` URL and send it to your friends.*

- **Localtunnel (Free with Node.js):**
  ```powershell
  npx localtunnel --port 8000
  ```

- **Ngrok:**
  ```powershell
  ngrok http 8000
  ```

---

## 🎮 Controls

| Action | Keyboard | Touch / Mobile |
| :--- | :--- | :--- |
| **Steer Snake** | <kbd>W</kbd> <kbd>A</kbd> <kbd>S</kbd> <kbd>D</kbd> or <kbd>↑</kbd> <kbd>←</kbd> <kbd>↓</kbd> <kbd>→</kbd> | On-Screen D-Pad (▲ ◀ ▼ ▶) |
| **Respawn (Multiplayer)** | <kbd>SPACE</kbd> | Action Button (⚡) |
| **Quick Taunts** | <kbd>1</kbd>, <kbd>2</kbd>, <kbd>3</kbd>, <kbd>4</kbd>, <kbd>5</kbd> | Taunt Buttons on Sidebar |
| **Pause (Solo Arcade)** | <kbd>SPACE</kbd> or <kbd>P</kbd> | Pause Button |
| **Toggle Sound** | Sound Button in Header | Sound Button |

---

## 📁 File Structure

```
snake_game_app/
│
├── app.py                # FastAPI web server, REST API & WebSocket endpoints
├── multiplayer.py        # Authoritative real-time multiplayer game engine & rooms
├── run.bat               # Windows 1-click launcher (binds to 0.0.0.0:8000)
├── requirements.txt      # Dependencies: fastapi, uvicorn, pydantic, websockets
├── snake_scores.db       # SQLite database for solo arcade scores
│
└── static/
    ├── index.html        # Modern Cyberpunk UI, Lobby & HUD
    ├── style.css         # Neon glowing responsive styling & animations
    └── game.js           # Multiplayer WebSocket client, canvas renderer, sound engine
```
