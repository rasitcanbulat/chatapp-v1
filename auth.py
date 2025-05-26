from flask import Blueprint, request, jsonify, current_app
import bcrypt
import jwt
import uuid

# ================================
# 🧩 Blueprint Oluşturucu
# ================================

def create_auth_blueprint(mysql, active_users):
    auth_bp = Blueprint('auth', __name__)

    # ================================
    # 📝 Kayıt Olma (POST /register)
    # ================================
    @auth_bp.route('/register', methods=['POST'])
    def register():
        data = request.json
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return jsonify({"error": "Eksik bilgi"}), 400

        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        existing = cursor.fetchone()

        if existing:
            return jsonify({"error": "Kullanıcı adı zaten var"}), 409

        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        user_uuid = str(uuid.uuid4())

        cursor.execute(
            "INSERT INTO users (uuid, username, password) VALUES (%s, %s, %s)",
            (user_uuid, username, hashed)
        )
        mysql.connection.commit()
        cursor.close()

        return jsonify({"message": "Kayıt başarılı", "uuid": user_uuid}), 201

    # ================================
    # 🔑 Giriş Yapma (POST /login)
    # ================================
    @auth_bp.route('/login', methods=['POST'])
    def login():
        data = request.json
        username = data.get('username')
        password = data.get('password')

        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()

        if not user:
            return jsonify({"error": "Kullanıcı bulunamadı"}), 404

        if not bcrypt.checkpw(password.encode('utf-8'), user[3].encode('utf-8')):
            return jsonify({"error": "Parola hatalı"}), 401

        token = jwt.encode(
            {"uuid": user[1]},
            current_app.config["SECRET_KEY"],
            algorithm="HS256"
        )

        # ➕ Aktif kullanıcı listesine ekle
        active_users.add(user[2])  # user[2] = username

        return jsonify({
            "token": token,
            "uuid": user[1],
            "username": user[2]
        }), 200

    # ================================
    # 🔁 Blueprint Return
    # ================================
    return auth_bp
