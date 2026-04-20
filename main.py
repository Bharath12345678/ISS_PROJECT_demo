import os
from dotenv import load_dotenv
from pymongo import MongoClient
import mysql.connector
from mysql.connector import pooling
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from utils.facial_recognition_module import find_closest_match
from fastapi.staticfiles import StaticFiles

load_dotenv()

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY"))
app.mount("/templates", StaticFiles(directory="templates"), name="templates")

mongo_client = MongoClient(os.getenv("MONGO_URI"))
db = mongo_client[os.getenv("MONGO_DB_NAME")]
collection = db["profile_images"]

db_pool = pooling.MySQLConnectionPool(
    pool_name="mainpool",
    pool_size=10,
    host=os.getenv("MYSQL_HOST"),
    user=os.getenv("MYSQL_USER"),
    password=os.getenv("MYSQL_PASSWORD"),
    database=os.getenv("MYSQL_DB")
)

class ConnectionManager:
    def __init__(self):
        self.active_connections = {}
        self.games = {}

    async def connect(self, websocket: WebSocket, uid: str):
        await websocket.accept()
        self.active_connections[uid] = websocket
        await self.broadcast_lobby()

    def disconnect(self, uid: str):
        if uid in self.active_connections:
            del self.active_connections[uid]

    async def send_personal_message(self, message: dict, uid: str):
        if uid in self.active_connections:
            await self.active_connections[uid].send_json(message)

    # async def broadcast_lobby(self):
    #     online_users = list(self.active_connections.keys())
    #     message = {"type": "lobby_update", "users": online_users}
    #     for connection in self.active_connections.values():
    #         await connection.send_json(message)
    # async def broadcast_lobby(self):
    #     conn = get_db()
    #     cursor = conn.cursor()
    #     cursor.execute("SELECT uid FROM users WHERE is_online=1")
    #     online_users = [row[0] for row in cursor.fetchall()]
    #     cursor.close()
    #     conn.close()
        
    #     message = {"type": "lobby_update", "users": online_users}
    #     for connection in self.active_connections.values():
    #         await connection.send_json(message)
    async def broadcast_lobby(self):
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT uid FROM users WHERE is_online=1")
        online_users = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()

        playing_users = set()
        for game in self.games.values():
            for player in game["players"]:
                playing_users.add(player)

        available_users = [u for u in online_users if u not in playing_users]

        message = {"type": "lobby_update", "users": available_users}
        for connection in self.active_connections.values():
            await connection.send_json(message)

manager = ConnectionManager()

def get_db():
    return db_pool.get_connection()

def calculate_elo(r1, r2, s1):
    e1 = 1 / (1 + 10 ** ((r2 - r1) / 400))
    e2 = 1 / (1 + 10 ** ((r1 - r2) / 400))
    s2 = 1.0 - s1
    new_r1 = r1 + 32 * (s1 - e1)
    new_r2 = r2 + 32 * (s2 - e2)
    return round(new_r1), round(new_r2)

def update_elo_db(uid1, uid2, s1):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT uid, elo_rating FROM users WHERE uid IN (%s, %s)", (uid1, uid2))
    rows = {row[0]: row[1] for row in cursor.fetchall()}

    if len(rows) == 2:
        r1 = rows[uid1]
        r2 = rows[uid2]

        new_r1, new_r2 = calculate_elo(r1, r2, s1)

        cursor.execute("UPDATE users SET elo_rating=%s WHERE uid=%s", (new_r1, uid1))
        cursor.execute("UPDATE users SET elo_rating=%s WHERE uid=%s", (new_r2, uid2))
        conn.commit()

    cursor.close()
    conn.close()

def set_offline(uid: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_online=0 WHERE uid=%s", (uid,))
    conn.commit()
    cursor.close()
    conn.close()

def check_win(board):
    lines = [
        [0, 1, 2], [3, 4, 5], [6, 7, 8],
        [0, 3, 6], [1, 4, 7], [2, 5, 8],
        [0, 4, 8], [2, 4, 6]
    ]
    for line in lines:
        if board[line[0]] and board[line[0]] == board[line[1]] == board[line[2]]:
            return board[line[0]]
    if "" not in board:
        return "Draw"
    return None

#In the /login endpoint inside main.py, we parse the incoming Base64 image using .split(",", 1). If the payload is malformed or missing the data:image/jpeg;base64, prefix for any reason, this will throw a ValueError and crash the endpoint
@app.get("/")
async def login_page():
    with open("templates/login.html", "r") as f:
        return HTMLResponse(content=f.read())
    
@app.get("/lobby")
async def lobby(request: Request):
    # return HTMLResponse("<h1>Lobby placeholder</h1>")
    if not request.session.get("uid"):
        return HTMLResponse(status_code=302, headers={"Location": "/"})
    with open("templates/lobby.html", "r") as f:
        return HTMLResponse(content=f.read())

@app.get("/leaderboard")
async def leaderboard_page():
    with open("templates/leaderboard.html", "r") as f:
        return HTMLResponse(content=f.read())

@app.get("/api/leaderboard")
async def get_leaderboard():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT uid, name, elo_rating FROM users ORDER BY elo_rating DESC")
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return JSONResponse(users)

@app.post("/login")
async def login(request: Request):
    body = await request.json()
    image_data = body.get("image")

    if not image_data or "," not in image_data:
        return JSONResponse({"success": False, "error": "Invalid image data"})

    db_images_dict = {}
    for doc in collection.find({}):
        db_images_dict[doc["uid"]] = doc["image"]

    header, encoded = image_data.split(",", 1)

    matched_uid = find_closest_match(encoded, db_images_dict)
    print("Matched UID:", matched_uid)

    if matched_uid:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT uid FROM users WHERE uid=%s", (matched_uid,))
        user = cursor.fetchone()

        if user:
            cursor.execute(
                "UPDATE users SET is_online=1 WHERE uid=%s",
                (matched_uid,)
            )
            conn.commit()

            request.session["uid"] = matched_uid

            cursor.close()
            conn.close()
            return JSONResponse({"success": True, "uid": matched_uid})

        cursor.close()
        conn.close()

    return JSONResponse({"success": False})

@app.websocket("/ws/{uid}")
async def websocket_endpoint(websocket: WebSocket, uid: str, request: Request):
    if request.session.get("uid") != uid:
        await websocket.close(code=4001)
        return
    await manager.connect(websocket, uid)
    current_room = None
    
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "challenge":
                target_uid = data.get("target")
                await manager.send_personal_message({
                    "type": "challenge_received",
                    "challenger": uid
                }, target_uid)

            # elif action == "accept_challenge":
            #     challenger_uid = data.get("challenger")
            #     room_id = os.urandom(8).hex()
            #     manager.games[room_id] = {
            #         "players": {challenger_uid: "X", uid: "O"},
            #         "board": [""] * 9,
            #         "turn": challenger_uid
            #     }
            #     current_room = room_id
                
            #     start_msg = {"type": "game_start", "room_id": room_id}
            #     await manager.send_personal_message(start_msg, challenger_uid)
            #     await manager.send_personal_message(start_msg, uid)
                
            #     state_msg = {
            #         "type": "game_state",
            #         "board": manager.games[room_id]["board"],
            #         "turn": manager.games[room_id]["turn"]
            #     }
            #     await manager.send_personal_message(state_msg, challenger_uid)
            #     await manager.send_personal_message(state_msg, uid)

            elif action == "accept_challenge":
                challenger_uid = data.get("challenger")
                
                if challenger_uid not in manager.active_connections:
                    await manager.send_personal_message({
                        "type": "error",
                        "message": "Challenger disconnected."
                    }, uid)
                    continue

                room_id = os.urandom(8).hex()
                manager.games[room_id] = {
                    "players": {challenger_uid: "X", uid: "O"},
                    "board": [""] * 9,
                    "turn": challenger_uid
                }
                current_room = room_id
                
                start_msg = {"type": "game_start", "room_id": room_id}
                await manager.send_personal_message(start_msg, challenger_uid)
                await manager.send_personal_message(start_msg, uid)
                
                state_msg = {
                    "type": "game_state",
                    "board": manager.games[room_id]["board"],
                    "turn": manager.games[room_id]["turn"]
                }
                await manager.send_personal_message(state_msg, challenger_uid)
                await manager.send_personal_message(state_msg, uid)
                
                await manager.broadcast_lobby()

            elif action == "decline_challenge":
                challenger_uid = data.get("challenger")
                await manager.send_personal_message({
                    "type": "challenge_declined",
                    "target": uid
                }, challenger_uid)

            elif action == "set_room":
                current_room = data.get("room_id")

            #the action == "move" WebSocket blocked us directly from accessing the board array using the position sent by the client. If client sends a string, a negative number, or an index greater than 8, game["board"][position] will trigger an IndexError or TypeError. This unhandled exception will crash that specific WebSocket connection.
            elif action == "move":
                room_id = data.get("room_id")
                position = data.get("position")
                game = manager.games.get(room_id)

                if game and game["turn"] == uid:
                    if isinstance(position, int) and 0 <= position <= 8 and game["board"][position] == "":
                        symbol = game["players"][uid]
                        game["board"][position] = symbol
                        
                        opponent = [p for p in game["players"] if p != uid][0]
                        game["turn"] = opponent

                        winner = check_win(game["board"])
                        
                        state_msg = {
                            "type": "game_state",
                            "board": game["board"],
                            "turn": game["turn"]
                        }
                        await manager.send_personal_message(state_msg, uid)
                        await manager.send_personal_message(state_msg, opponent)

                        # if winner:
                        #     if winner == "Draw":
                        #         update_elo_db(uid, opponent, 0.5)
                        #     else:
                        #         update_elo_db(uid, opponent, 1.0)
                            
                        #     over_msg = {"type": "game_over", "winner": winner}
                        #     await manager.send_personal_message(over_msg, uid)
                        #     await manager.send_personal_message(over_msg, opponent)
                        #     del manager.games[room_id]
                        #     current_room = None

                        if winner:
                            if winner == "Draw":
                                update_elo_db(uid, opponent, 0.5)
                                final_winner = "Draw"
                            else:
                                update_elo_db(uid, opponent, 1.0)
                                final_winner = uid 
                            
                            over_msg = {"type": "game_over", "winner": final_winner}
                            await manager.send_personal_message(over_msg, uid)
                            await manager.send_personal_message(over_msg, opponent)
                            del manager.games[room_id]
                            current_room = None
                            await manager.broadcast_lobby()

    except WebSocketDisconnect:
        manager.disconnect(uid)
        set_offline(uid)
        await manager.broadcast_lobby()
        
        if current_room and current_room in manager.games:
            game = manager.games[current_room]
            if uid in game["players"]:
                opponent = [p for p in game["players"] if p != uid][0]
                update_elo_db(opponent, uid, 1.0)
                await manager.send_personal_message({
                    "type": "game_over",
                    "winner": "forfeit"
                }, opponent)
                del manager.games[current_room]