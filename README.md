# 💬 ChatApp

**ChatApp**, Flask + WebSocket + WebRTC + MySQL teknolojileri ile geliştirilmiş, gerçek zamanlı ve güvenli bir sohbet & sesli arama platformudur. Kullanıcılar arasında özel/grup mesajlaşma, sesli görüşme ve e-posta ile 2FA doğrulama desteklenmektedir.

---

## 🚀 Özellikler

- 🔐 JWT tabanlı kullanıcı kayıt ve giriş
- ✉️ E-posta ile 2 Faktörlü Doğrulama (2FA)
- 👤 Aktif kullanıcı takibi (Socket.IO ile canlı liste)
- 💬 Gerçek zamanlı bireysel ve grup sohbeti
- 🔒 Uçtan uca AES ile mesaj şifreleme (E2EE)
- 📞 WebRTC tabanlı tarayıcı içi sesli arama
- ⏱️ Çağrı süresi ve geçmiş kaydı
- ✅ Mesaj okundu bilgisi (✓ / ✓✓)
- 🗂️ MySQL ile veritabanı desteği
- 🎨 Responsive ve sade arayüz tasarımı

---

## 📁 Proje Yapısı

```
chatapp/
├── app.py
├── auth.py
├── config.py
├── static/
│   ├── main.js
│   └── ...
├── templates/
│   ├── login.html
│   ├── register.html
│   └── home.html
├── .env
└── README.md
```

---

## ⚙️ Kurulum

```bash
git clone https://github.com/rasitcanbulat/ChatApp.git
cd ChatApp
python -m venv venv
venv\Scripts\activate       # (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
```

### `.env` Dosyası:

```env
SECRET_KEY=senin-secret-keyin
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_DB=chatapp
```

---

## 🗃️ Veritabanı Tabloları

### 🔑 `users`

```sql
CREATE TABLE users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  uuid VARCHAR(36) UNIQUE,
  username VARCHAR(255) UNIQUE,
  email VARCHAR(255),
  password VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 💬 `messages`

```sql
CREATE TABLE messages (
  id INT AUTO_INCREMENT PRIMARY KEY,
  room VARCHAR(100),
  sender VARCHAR(100),
  message TEXT,
  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  is_read TINYINT(1) DEFAULT 0
);
```

### 👥 `groups`

```sql
CREATE TABLE groups (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(255) UNIQUE,
  owner_uuid VARCHAR(36),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 👤 `group_members`

```sql
CREATE TABLE group_members (
  group_id INT,
  user_uuid VARCHAR(36),
  joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (group_id, user_uuid)
);
```

### 📞 `call_logs`

```sql
CREATE TABLE call_logs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  caller VARCHAR(50),
  callee VARCHAR(50),
  start_time DATETIME,
  end_time DATETIME,
  duration_seconds INT
);
```

---

## ▶️ Uygulama Nasıl Başlatılır?

```bash
python app.py
```

Uygulama şurada çalışacaktır: [http://localhost:5000](http://localhost:5000)

---

## 📬 Not: E-Posta Doğrulama

- Gmail için [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) üzerinden uygulama şifresi almanız gerekir.
- `auth.py` içinde `sender_email` ve `sender_password` bilgilerini girerek kodların kullanıcıya e-posta ile ulaşması sağlanır.

---

## 👨‍💻 Geliştirici

Bu proje, **[@rasitcanbulat](https://www.linkedin.com/in/rasitcanbulat/)** tarafından geliştirilmiştir.
