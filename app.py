from flask import Flask, render_template, jsonify
from flask_cors import CORS
from flask_mysqldb import MySQL
from flask_socketio import SocketIO, emit, join_room, disconnect
from flask import request
from config import Config  # config.py dosyanızı doğru şekilde import ettiğinizden emin olun

app = Flask(__name__)
app.config.from_object(Config)
CORS(app)  # CORS'un tüm kaynaklara izin verdiğinden emin olun (geliştirme için)

mysql = MySQL(app)
socketio = SocketIO(app, cors_allowed_origins="*")  # CORS'u burada da etkinleştir

# 🔹 Aktif kullanıcılar RAM'de tutulur
active_users = set()

# 🔹 Socket ID eşlemesi: { sid: username }
# Bu harita, bir Socket ID'sinin hangi kullanıcıya ait olduğunu tutar.
socket_sid_map = {}

# 🔹 Blueprint tanımlama
from auth import create_auth_blueprint

app.register_blueprint(create_auth_blueprint(mysql, active_users), url_prefix="/api/auth")


# 🔹 Sayfa Rotaları
@app.route("/")
def login_page():
    return render_template("login.html")


@app.route("/register")
def register_page():
    return render_template("register.html")


@app.route("/home")
def home_page():
    return render_template("home.html")


# 🔹 Aktif kullanıcıları döndür
@app.route("/api/users/active")
def get_active_users():
    return jsonify([{"username": u} for u in active_users])


# 🔹 Socket.IO Olay İşleyicileri

@socketio.on("connect")
def handle_connect():
    print(f"Client connected: {request.sid}")


@socketio.on("register_socket")
def handle_register_socket(data):
    username = data.get("username")
    if username:
        # Eski bir SID varsa önce onu kaldır, sonra yeni SID'yi ekle
        # Bu, aynı kullanıcının farklı bir sekmeden bağlanması durumunda eski oturumu temizler.
        # Ancak, aynı kullanıcının birden fazla aktif oturumuna izin vermek istiyorsanız bu mantığı değiştirmeniz gerekir.
        for sid, uname in list(socket_sid_map.items()):
            if uname == username and sid != request.sid:
                del socket_sid_map[sid]
                print(f"Removed old SID {sid} for user {username}")

        socket_sid_map[request.sid] = username
        active_users.add(username)
        print(f"User {username} registered with SID {request.sid}. Active users: {active_users}")
        emit("active_users_update", {"users": list(active_users)}, broadcast=True)
    else:
        print("Register socket failed: No username provided.")


@socketio.on("disconnect")
def handle_disconnect():
    disconnected_sid = request.sid
    if disconnected_sid in socket_sid_map:
        username = socket_sid_map[disconnected_sid]
        active_users.discard(username)  # Set'ten kaldır
        del socket_sid_map[disconnected_sid]  # Haritadan kaldır
        print(f"User {username} disconnected. SID: {disconnected_sid}. Active users: {active_users}")
        # Aktif kullanıcı listesini güncelle
        emit("active_users_update", {"users": list(active_users)}, broadcast=True)
    else:
        print(f"Unknown SID disconnected: {disconnected_sid}")


@socketio.on("private_message")
def handle_private_message(data):
    to_user = data.get("to")
    message = data.get("message")
    from_user = socket_sid_map.get(request.sid)

    if from_user and to_user and message:
        target_sid = None
        for sid, username in socket_sid_map.items():
            if username == to_user:
                target_sid = sid
                break

        # 📝 Mesajı veritabanına kaydet
        room_name = f"{min(from_user, to_user)}-{max(from_user, to_user)}"
        cursor = mysql.connection.cursor()
        cursor.execute(
            "INSERT INTO messages (room, sender, message) VALUES (%s, %s, %s)",
            (room_name, from_user, message)
        )
        mysql.connection.commit()
        cursor.close()

        if target_sid:
            emit("private_message", {"from": from_user, "message": message}, room=target_sid)
        print(f"Private message from {from_user} to {to_user}: {message}")
    else:
        print("Invalid private message data.")



@socketio.on("group_message")
def handle_group_message(data):
    group_name = data.get("group")
    message = data.get("message")
    from_user = socket_sid_map.get(request.sid)

    if from_user and group_name and message:
        # 🔥 Veritabanına kaydet
        cursor = mysql.connection.cursor()
        cursor.execute(
            "INSERT INTO messages (room, sender, message) VALUES (%s, %s, %s)",
            (group_name, from_user, message)
        )
        mysql.connection.commit()
        cursor.close()

        # Mesajı odaya ilet
        emit("group_message", {
            "from": from_user,
            "group": group_name,
            "message": message
        }, room=group_name, skip_sid=request.sid)

        print(f"[GROUP] {from_user} → {group_name}: {message}")
    else:
        print("Geçersiz grup mesajı verisi.")



@socketio.on("create_group")
def handle_create_group(data):
    group_name = data.get("group_name")
    members = data.get("members", [])
    from_user = socket_sid_map.get(request.sid)

    if not group_name or not from_user:
        print("Eksik grup bilgisi.")
        return

    members.append(from_user)  # Grup kurucusunu da ekle
    members = list(set(members))  # Tekrar varsa kaldır

    # UUID'leri bulmak için kullanıcı adlarını sorgula
    cursor = mysql.connection.cursor()
    format_strings = ','.join(['%s'] * len(members))
    cursor.execute(f"SELECT uuid, username FROM users WHERE username IN ({format_strings})", tuple(members))
    user_map = {row[1]: row[0] for row in cursor.fetchall()}

    # Grup kaydı
    cursor.execute("SELECT uuid FROM users WHERE username = %s", (from_user,))
    owner_uuid = cursor.fetchone()[0]
    cursor.execute("INSERT INTO groups (name, owner_uuid) VALUES (%s, %s)", (group_name, owner_uuid))
    group_id = cursor.lastrowid

    # Üyeleri kaydet
    for username in members:
        user_uuid = user_map.get(username)
        if user_uuid:
            cursor.execute("INSERT INTO group_members (group_id, user_uuid) VALUES (%s, %s)", (group_id, user_uuid))

    mysql.connection.commit()
    cursor.close()

    # Gruptaki aktif üyelere emit et
    for sid, username in socket_sid_map.items():
        if username in members:
            emit("group_created", {"group_name": group_name}, room=sid)

    print(f"Grup '{group_name}' oluşturuldu. Üyeler: {members}")


@socketio.on("join_group")
def handle_join_group(data):
    group = data.get("group")
    if group:
        join_room(group)
        print(f"{request.sid} joined group room '{group}'")
    else:
        print("Join group failed: No group name provided.")

@socketio.on("delete_group")
def handle_delete_group(data):
    group_name = data.get("group_name")
    from_user = socket_sid_map.get(request.sid)

    if not group_name or not from_user:
        return

    cursor = mysql.connection.cursor()

    # Kullanıcının owner olup olmadığını kontrol et
    cursor.execute("SELECT g.id FROM groups g JOIN users u ON g.owner_uuid = u.uuid WHERE g.name = %s AND u.username = %s", (group_name, from_user))
    row = cursor.fetchone()
    if not row:
        cursor.close()
        emit("group_delete_error", {"error": "Yetkiniz yok!"}, room=request.sid)
        return

    group_id = row[0]

    # Grup mesajlarını ve üyeliklerini sil
    cursor.execute("DELETE FROM messages WHERE room = %s", (group_name,))
    cursor.execute("DELETE FROM group_members WHERE group_id = %s", (group_id,))
    cursor.execute("DELETE FROM groups WHERE id = %s", (group_id,))
    mysql.connection.commit()
    cursor.close()

    # Tüm kullanıcılara bildir
    emit("group_deleted", {"group_name": group_name}, broadcast=True)

@app.route("/api/groups/<username>")
def get_user_groups(username):
    cursor = mysql.connection.cursor()

    # Kullanıcının UUID'sini al
    cursor.execute("SELECT uuid FROM users WHERE username = %s", (username,))
    user_row = cursor.fetchone()
    if not user_row:
        cursor.close()
        return jsonify([])

    user_uuid = user_row[0]

    # Kullanıcının dahil olduğu grupları ve sahiplik bilgilerini getir
    cursor.execute("""
        SELECT g.name, g.owner_uuid = %s AS is_owner
        FROM groups g
        JOIN group_members gm ON g.id = gm.group_id
        WHERE gm.user_uuid = %s
    """, (user_uuid, user_uuid))

    groups = [{"name": row[0], "is_owner": bool(row[1])} for row in cursor.fetchall()]
    cursor.close()
    return jsonify(groups)


@app.route("/api/messages/group/<group_name>")
def get_group_messages(group_name):
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT sender, message, timestamp FROM messages WHERE room = %s ORDER BY timestamp ASC", (group_name,))
    rows = cursor.fetchall()
    cursor.close()
    return jsonify([
        {
            "sender": r[0],
            "message": r[1],
            "timestamp": r[2].strftime("%H:%M")
        } for r in rows
    ])


# 🔹 WebRTC Sinyalizasyon İşleyicileri

@socketio.on("call-offer")
def handle_call_offer(data):
    to_user = data.get("to")
    offer = data.get("offer")
    from_user = socket_sid_map.get(request.sid)

    if from_user and to_user and offer:
        target_sid = None
        for sid, username in socket_sid_map.items():
            if username == to_user:
                target_sid = sid
                break

        if target_sid:
            emit("call-offer", {
                "from": from_user,
                "offer": offer
            }, room=target_sid)
            print(f"Call offer from {from_user} to {to_user}")
        else:
            # Hedef kullanıcı aktif değilse veya bulunamazsa arayana bildir
            print(f"User {to_user} not found or not active to receive call offer from {from_user}.")
            emit("call-rejected", {"from": to_user, "reason": "Not available"}, room=request.sid)
    else:
        print("Invalid call offer data.")


@socketio.on("call-answer")
def handle_call_answer(data):
    to_user = data.get("to")
    answer = data.get("answer")
    from_user = socket_sid_map.get(request.sid)

    if from_user and to_user and answer:
        target_sid = None
        for sid, username in socket_sid_map.items():
            if username == to_user:
                target_sid = sid
                break

        if target_sid:
            emit("call-answer", {
                "from": from_user,
                "answer": answer
            }, room=target_sid)
            print(f"Call answer from {from_user} to {to_user}")
        else:
            print(f"User {to_user} not found or not active to receive call answer from {from_user}.")
    else:
        print("Invalid call answer data.")


@socketio.on("ice-candidate")
def handle_ice_candidate(data):
    to_user = data.get("to")
    candidate = data.get("candidate")
    from_user = socket_sid_map.get(request.sid)

    if from_user and to_user and candidate:
        target_sid = None
        for sid, username in socket_sid_map.items():
            if username == to_user:
                target_sid = sid
                break

        if target_sid:
            emit("ice-candidate", {
                "from": from_user,
                "candidate": candidate
            }, room=target_sid)
            print(f"ICE candidate from {from_user} to {to_user}")
        else:
            print(f"User {to_user} not found or not active to receive ICE candidate from {from_user}.")
    else:
        print("Invalid ICE candidate data.")


@socketio.on("call-rejected")
def handle_call_rejected(data):
    to_user = data.get("to")
    reason = data.get("reason", "unknown")
    from_user = socket_sid_map.get(request.sid)

    if from_user and to_user:
        target_sid = None
        for sid, username in socket_sid_map.items():
            if username == to_user:
                target_sid = sid
                break

        if target_sid:
            emit("call-rejected", {
                "from": from_user,
                "reason": reason
            }, room=target_sid)
            print(f"Call from {from_user} rejected by {to_user} (Reason: {reason})")
        else:
            print(f"User {to_user} not found or not active to receive call rejection from {from_user}.")
    else:
        print("Invalid call rejected data.")


@socketio.on("call-ended")
def handle_call_ended(data):
    to_user = data.get("to")
    from_user = socket_sid_map.get(request.sid)

    if from_user and to_user:
        target_sid = None
        for sid, username in socket_sid_map.items():
            if username == to_user:
                target_sid = sid
                break

        if target_sid:
            emit("call-ended", {
                "from": from_user
            }, room=target_sid)
            print(f"Call from {from_user} ended by {from_user} to {to_user}")
        else:
            print(f"User {to_user} not found or not active to receive call ended signal from {from_user}.")
    else:
        print("Invalid call ended data.")

@app.route("/api/messages/private/<user1>/<user2>")
def get_private_messages(user1, user2):
    room_name = f"{min(user1, user2)}-{max(user1, user2)}"
    cursor = mysql.connection.cursor()

    # 1. Mesajları çek
    cursor.execute("SELECT id, sender, message, timestamp, is_read FROM messages WHERE room = %s ORDER BY timestamp ASC", (room_name,))
    rows = cursor.fetchall()

    # 2. Okunmamış karşı taraf mesajlarını işaretle
    cursor.execute("""
        UPDATE messages 
        SET is_read = TRUE 
        WHERE room = %s AND sender = %s AND is_read = FALSE
    """, (room_name, user2))  # user2 gönderici ise okundu sayılır

    mysql.connection.commit()
    cursor.close()

    return jsonify([
        {
            "id": r[0],
            "sender": r[1],
            "message": r[2],
            "timestamp": r[3].strftime("%H:%M"),
            "is_read": r[4]
        } for r in rows
    ])


if __name__ == "__main__":
    socketio.run(app, debug=True, port=5000, allow_unsafe_werkzeug=True)

