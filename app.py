from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from flask_mysqldb import MySQL
from flask_socketio import SocketIO, emit, join_room
from config import Config
from auth import create_auth_blueprint

# ================================
# 🔧 Uygulama ve Config Kurulumu
# ================================

app = Flask(__name__)
app.config.from_object(Config)
CORS(app)
mysql = MySQL(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# ================================
# 🧠 Global Veriler
# ================================

active_users = set()
socket_sid_map = {}  # {sid: username}

# ================================
# 📦 Blueprint Kayıt
# ================================

app.register_blueprint(create_auth_blueprint(mysql, active_users), url_prefix="/api/auth")

# ================================
# 🌐 Sayfa Rotaları
# ================================

@app.route("/")
def login_page():
    return render_template("login.html")

@app.route("/register")
def register_page():
    return render_template("register.html")

@app.route("/home")
def home_page():
    return render_template("home.html")

# ================================
# 👥 Aktif Kullanıcılar
# ================================

@app.route("/api/users/active")
def get_active_users():
    return jsonify([{"username": u} for u in active_users])

# ================================
# 🔌 Socket.IO: Bağlantılar
# ================================

@socketio.on("connect")
def handle_connect():
    print(f"Client connected: {request.sid}")

@socketio.on("disconnect")
def handle_disconnect():
    disconnected_sid = request.sid
    username = socket_sid_map.pop(disconnected_sid, None)
    if username:
        active_users.discard(username)
        print(f"{username} disconnected.")
        emit("active_users_update", {"users": list(active_users)}, broadcast=True)

@socketio.on("register_socket")
def handle_register_socket(data):
    username = data.get("username")
    if not username:
        return
    for sid, uname in list(socket_sid_map.items()):
        if uname == username:
            del socket_sid_map[sid]
    socket_sid_map[request.sid] = username
    active_users.add(username)
    emit("active_users_update", {"users": list(active_users)}, broadcast=True)

# ================================
# 💬 Özel Mesajlaşma
# ================================

@socketio.on("private_message")
def handle_private_message(data):
    to_user = data.get("to")
    message = data.get("message")
    from_user = socket_sid_map.get(request.sid)

    if not all([to_user, message, from_user]):
        return

    room_name = f"{min(from_user, to_user)}-{max(from_user, to_user)}"
    cursor = mysql.connection.cursor()
    cursor.execute("INSERT INTO messages (room, sender, message) VALUES (%s, %s, %s)", (room_name, from_user, message))
    mysql.connection.commit()
    cursor.close()

    for sid, username in socket_sid_map.items():
        if username == to_user:
            emit("private_message", {"from": from_user, "message": message}, room=sid)
            break

@app.route("/api/messages/private/<user1>/<user2>")
def get_private_messages(user1, user2):
    room_name = f"{min(user1, user2)}-{max(user1, user2)}"
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT id, sender, message, timestamp, is_read FROM messages WHERE room = %s ORDER BY timestamp ASC", (room_name,))
    rows = cursor.fetchall()
    cursor.execute("UPDATE messages SET is_read = TRUE WHERE room = %s AND sender = %s AND is_read = FALSE", (room_name, user2))
    mysql.connection.commit()
    cursor.close()
    return jsonify([{"id": r[0], "sender": r[1], "message": r[2], "timestamp": r[3].strftime("%H:%M"), "is_read": r[4]} for r in rows])

@socketio.on("messages_read")
def handle_messages_read(data):
    reader = data.get("reader")
    sender = data.get("sender")
    if not reader or not sender:
        return
    room_name = f"{min(reader, sender)}-{max(reader, sender)}"
    cursor = mysql.connection.cursor()
    cursor.execute("UPDATE messages SET is_read = TRUE WHERE room = %s AND sender = %s AND is_read = FALSE", (room_name, sender))
    mysql.connection.commit()
    cursor.close()
    for sid, username in socket_sid_map.items():
        if username == sender:
            emit("messages_read_receipt", {"reader": reader}, room=sid)
            break

# ================================
# 📟 Çağrı Geçmişi
# ================================

@app.route("/api/call-log", methods=["POST"])
def save_call_log():
    data = request.json
    caller = data.get("caller")
    callee = data.get("callee")
    start_time = data.get("start_time")
    end_time = data.get("end_time")

    from datetime import datetime
    fmt = "%Y-%m-%d %H:%M:%S"
    start_dt = datetime.strptime(start_time, fmt)
    end_dt = datetime.strptime(end_time, fmt)
    duration = int((end_dt - start_dt).total_seconds())

    cursor = mysql.connection.cursor()
    cursor.execute("""
        INSERT INTO call_logs (caller, callee, start_time, end_time, duration_seconds)
        VALUES (%s, %s, %s, %s, %s)
    """, (caller, callee, start_time, end_time, duration))
    mysql.connection.commit()
    cursor.close()

    return jsonify({"message": "Görüşme kaydedildi."})

@app.route("/api/call-log/<username>")
def get_call_history(username):
    cursor = mysql.connection.cursor()
    cursor.execute("""
        SELECT caller, callee, start_time, end_time, duration_seconds
        FROM call_logs
        WHERE caller = %s OR callee = %s
        ORDER BY start_time DESC
    """, (username, username))
    rows = cursor.fetchall()
    cursor.close()

    return jsonify([
        {
            "caller": r[0],
            "callee": r[1],
            "start_time": r[2].strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": r[3].strftime("%Y-%m-%d %H:%M:%S"),
            "duration": r[4]
        }
        for r in rows
    ])

# ================================
# 👨‍👩‍👧‍👦 Grup Sohbeti
# ================================

@socketio.on("group_message")
def handle_group_message(data):
    group = data.get("group")
    message = data.get("message")
    from_user = socket_sid_map.get(request.sid)
    if not all([group, message, from_user]):
        return
    cursor = mysql.connection.cursor()
    cursor.execute("INSERT INTO messages (room, sender, message) VALUES (%s, %s, %s)", (group, from_user, message))
    mysql.connection.commit()
    cursor.close()
    emit("group_message", {"from": from_user, "group": group, "message": message}, room=group, skip_sid=request.sid)

@app.route("/api/messages/group/<group_name>")
def get_group_messages(group_name):
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT sender, message, timestamp FROM messages WHERE room = %s ORDER BY timestamp ASC", (group_name,))
    rows = cursor.fetchall()
    cursor.close()
    return jsonify([{ "sender": r[0], "message": r[1], "timestamp": r[2].strftime("%H:%M") } for r in rows])

@socketio.on("create_group")
def handle_create_group(data):
    group_name = data.get("group_name")
    members = list(set(data.get("members", []) + [socket_sid_map.get(request.sid)]))
    if not group_name or not members:
        return
    cursor = mysql.connection.cursor()
    format_strings = ','.join(['%s'] * len(members))
    cursor.execute(f"SELECT uuid, username FROM users WHERE username IN ({format_strings})", tuple(members))
    user_map = {row[1]: row[0] for row in cursor.fetchall()}
    cursor.execute("SELECT uuid FROM users WHERE username = %s", (socket_sid_map.get(request.sid),))
    owner_uuid = cursor.fetchone()[0]
    cursor.execute("INSERT INTO groups (name, owner_uuid) VALUES (%s, %s)", (group_name, owner_uuid))
    group_id = cursor.lastrowid
    for username in members:
        if username in user_map:
            cursor.execute("INSERT INTO group_members (group_id, user_uuid) VALUES (%s, %s)", (group_id, user_map[username]))
    mysql.connection.commit()
    cursor.close()
    for sid, username in socket_sid_map.items():
        if username in members:
            emit("group_created", {"group_name": group_name}, room=sid)

@socketio.on("join_group")
def handle_join_group(data):
    join_room(data.get("group"))

@socketio.on("delete_group")
def handle_delete_group(data):
    group = data.get("group_name")
    from_user = socket_sid_map.get(request.sid)
    if not group or not from_user:
        return
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT g.id FROM groups g JOIN users u ON g.owner_uuid = u.uuid WHERE g.name = %s AND u.username = %s", (group, from_user))
    row = cursor.fetchone()
    if not row:
        emit("group_delete_error", {"error": "Yetkiniz yok!"}, room=request.sid)
        cursor.close()
        return
    group_id = row[0]
    cursor.execute("DELETE FROM messages WHERE room = %s", (group,))
    cursor.execute("DELETE FROM group_members WHERE group_id = %s", (group_id,))
    cursor.execute("DELETE FROM groups WHERE id = %s", (group_id,))
    mysql.connection.commit()
    cursor.close()
    emit("group_deleted", {"group_name": group}, broadcast=True)

@app.route("/api/groups/<username>")
def get_user_groups(username):
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT uuid FROM users WHERE username = %s", (username,))
    user_row = cursor.fetchone()
    if not user_row:
        return jsonify([])
    user_uuid = user_row[0]
    cursor.execute("""
        SELECT g.name, g.owner_uuid = %s AS is_owner
        FROM groups g
        JOIN group_members gm ON g.id = gm.group_id
        WHERE gm.user_uuid = %s
    """, (user_uuid, user_uuid))
    groups = [{"name": row[0], "is_owner": bool(row[1])} for row in cursor.fetchall()]
    cursor.close()
    return jsonify(groups)

# ================================
# 📞 WebRTC - Çağrı İşleyicileri
# ================================

@socketio.on("call-offer")
def handle_call_offer(data):
    to_user = data.get("to")
    offer = data.get("offer")
    from_user = socket_sid_map.get(request.sid)
    if from_user and to_user and offer:
        for sid, username in socket_sid_map.items():
            if username == to_user:
                emit("call-offer", {"from": from_user, "offer": offer}, room=sid)
                return
        emit("call-rejected", {"from": to_user, "reason": "Not available"}, room=request.sid)

@socketio.on("call-answer")
def handle_call_answer(data):
    to_user = data.get("to")
    answer = data.get("answer")
    from_user = socket_sid_map.get(request.sid)
    for sid, username in socket_sid_map.items():
        if username == to_user:
            emit("call-answer", {"from": from_user, "answer": answer}, room=sid)
            return

@socketio.on("ice-candidate")
def handle_ice_candidate(data):
    to_user = data.get("to")
    candidate = data.get("candidate")
    from_user = socket_sid_map.get(request.sid)
    for sid, username in socket_sid_map.items():
        if username == to_user:
            emit("ice-candidate", {"from": from_user, "candidate": candidate}, room=sid)
            return

@socketio.on("call-rejected")
def handle_call_rejected(data):
    to_user = data.get("to")
    reason = data.get("reason")
    from_user = socket_sid_map.get(request.sid)
    for sid, username in socket_sid_map.items():
        if username == to_user:
            emit("call-rejected", {"from": from_user, "reason": reason}, room=sid)
            return

@socketio.on("call-ended")
def handle_call_ended(data):
    to_user = data.get("to")
    from_user = socket_sid_map.get(request.sid)
    for sid, username in socket_sid_map.items():
        if username == to_user:
            emit("call-ended", {"from": from_user}, room=sid)
            return

# ================================
# 🚀 Uygulama Başlatıcı
# ================================

if __name__ == "__main__":
    socketio.run(app, debug=True, port=5000, allow_unsafe_werkzeug=True)
