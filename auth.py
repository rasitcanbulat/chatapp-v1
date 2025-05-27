from flask import Blueprint, request, jsonify, current_app
import bcrypt
import jwt
import uuid
import smtplib
import random
from email.mime.text import MIMEText
pending_codes = {}  # username -> 6 haneli kod
# ================================
# 🧩 Blueprint Oluşturucu
# ================================

def send_verification_code(email, code):
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    sender_email = "baruinovasyon@gmail.com"  # KENDİ GMAİL'İN
    sender_password = "orpjveuoorvaqpnr"  # Google’dan aldığın uygulama şifresi

    msg = MIMEText(f"ChatApp giriş doğrulama kodunuz: {code}")
    msg["Subject"] = "ChatApp Giriş Doğrulama"
    msg["From"] = sender_email
    msg["To"] = email

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, email, msg.as_string())
        server.quit()
        print(f"✅ Mail gönderildi: {email} → Kod: {code}")
    except Exception as e:
        print("❌ Mail gönderilemedi:", e)

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
        email = data.get('email')

        if not username or not password or not email:
            return jsonify({"error": "Eksik bilgi"}), 400

        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        existing = cursor.fetchone()

        if existing:
            return jsonify({"error": "Kullanıcı adı zaten var"}), 409

        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        user_uuid = str(uuid.uuid4())

        cursor.execute(
            "INSERT INTO users (uuid, username, email, password) VALUES (%s, %s, %s, %s)",
            (user_uuid, username, email, hashed)
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
        cursor.execute("SELECT uuid, username, email, password FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()

        if not user:
            return jsonify({"error": "Kullanıcı bulunamadı"}), 404

        if not bcrypt.checkpw(password.encode('utf-8'), user[3].encode('utf-8')):
            return jsonify({"error": "Parola hatalı"}), 401

        # 🔐 Kod üret ve gönder
        code = str(random.randint(100000, 999999))
        pending_codes[username] = code
        send_verification_code(user[2], code)

        return jsonify({"message": "Kod gönderildi"})

    # ================================
    # 🔑 Kod Doğrulama (Verify Code)
    # ================================
    @auth_bp.route('/verify-code', methods=['POST'])
    def verify_code():
        data = request.json
        username = data.get("username")
        code = data.get("code")

        if not username or not code:
            return jsonify({"error": "Eksik bilgi"}), 400

        if pending_codes.get(username) != code:
            return jsonify({"error": "Kod hatalı"}), 401

        del pending_codes[username]

        cursor = mysql.connection.cursor()
        cursor.execute("SELECT uuid FROM users WHERE username = %s", (username,))
        row = cursor.fetchone()
        cursor.close()

        if not row:
            return jsonify({"error": "Kullanıcı bulunamadı"}), 404

        user_id = row[0]
        token = jwt.encode({"uuid": user_id}, current_app.config["SECRET_KEY"], algorithm="HS256")

        return jsonify({
            "token": token,
            "username": username
        }), 200

    # ================================
    # 🔁 Blueprint Return
    # ================================
    return auth_bp
