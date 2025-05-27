// Ortak gizli anahtar (örnek)
const SECRET_KEY = "J38sdf9h1!ks8LD$Xxk09g1h2@w9sdf1kq";

// AES ile şifreleme
function encryptMessage(message) {
    return CryptoJS.AES.encrypt(message, SECRET_KEY).toString();
}

// AES ile çözme
function decryptMessage(encrypted) {
    const bytes = CryptoJS.AES.decrypt(encrypted, SECRET_KEY);
    return bytes.toString(CryptoJS.enc.Utf8);
}

/* ================================================
🟢 GLOBAL DEĞİŞKENLER VE BAŞLANGIÇ AYARLARI
================================================= */
const socket = io();
let currentChatUser = null; // Şu anki özel sohbet kullanıcısı
let currentChatGroup = null; // Şu anki grup sohbeti
let currentUser = null; // Giriş yapan kullanıcı adı
let peerConnection = null; // RTCPeerConnection objesi
let localStream = null; // Yerel ses akışı
let pendingCandidates = []; // Uzak açıklama gelmeden önce gelen ICE adayları
let isCalling = false; // Arama yapılıyor mu?
let isReceivingCall = false; // Arama alınıyor mu?
let targetUser = null; // Aranan veya arayan kişi

// Sayfa yüklendiğinde çalışacak fonksiyon
function loadHome() {
  currentUser = sessionStorage.getItem("username");
  if (!currentUser) {
    window.location.href = "/";
    return;
  }

  const span = document.getElementById("current-user");
  if (span) span.innerText = `Hoş geldiniz, ${currentUser}`;

  const sidebar = document.getElementById("current-user-sidebar");
  if (sidebar) sidebar.innerText = currentUser;

  socket.emit("register_socket", { username: currentUser });

  fetchActiveUsers();
  loadUserGroups();
}


/* ================================================
🟢 KULLANICI VE GRUP YÖNETİMİ FONKSİYONLARI
================================================= */

// Aktif kullanıcıları sunucudan çeker
async function fetchActiveUsers() {
    try {
        const response = await fetch("/api/users/active");
        const users = await response.json();
        updateUserList(users.map(u => u.username));
    } catch (error) {
        console.error("Aktif kullanıcılar getirilirken hata:", error);
    }
}

// Kullanıcı listesini günceller ve arama butonlarını ekler
function updateUserList(users) {
    const userListDiv = document.getElementById("user-list");
    userListDiv.innerHTML = `<div class="left-panel-header"> <h3>Aktif Kullanıcılar</h3>
    <button class="group-btn-inline" onclick="openCreateGroupModal()">+ Grup</button>
  </div>`;
    users.forEach(user => {
        if (user !== currentUser) { // Kendi kendini listeleme
            const userItem = document.createElement("div");
            userItem.className = "user-item call-button";  // aynı buton stili uygula
            userItem.innerText = user;
            userItem.onclick = () => openPrivateChat(user);

            // Arama butonu ekle
            const callButton = document.createElement("button");
            callButton.innerText = "Ara";
            callButton.className = "call-button"; // Stil için bir sınıf ekle
            callButton.onclick = (e) => {
                e.stopPropagation(); // userItem'in click olayını engelle
                startCall(user);
            };
            userItem.appendChild(callButton);

            userListDiv.appendChild(userItem);
        }
    });
}

// Belirli bir kullanıcı ile özel sohbeti başlatır ve mesaj geçmişini yükler
function openPrivateChat(username) {
    currentChatUser = username;
    currentChatGroup = null;
    document.getElementById("chat-window").innerHTML = `
        <h2>${username} ile Özel Sohbet</h2>
        <p style="font-size: 13px; color: gray; margin-top: -10px; margin-bottom: 15px;">
            🔐 Bu sohbet uçtan uca şifreleme ile korunmaktadır.
        </p>
    `;

    fetch(`/api/messages/private/${currentUser}/${username}`)
        .then(res => res.json())
        .then(messages => {
            const chatWindow = document.getElementById("chat-window");
            messages.forEach(msg => {
                const p = document.createElement("p");
                p.id = `msg-${msg.id}`;
                p.className = msg.sender === currentUser ? "message-right" : "message-left";

                let readMark = "";
                if (msg.sender === currentUser) {
                    readMark = msg.is_read ? " ✅✅" : " ✅";
                }

                const decrypted = decryptMessage(msg.message);
                console.log("🔓 Çözülmüş mesaj:", decrypted);
                p.innerText = `[${msg.sender} - ${msg.timestamp}]: ${decrypted}${readMark}`;
                chatWindow.appendChild(p);
            });
            chatWindow.scrollTop = chatWindow.scrollHeight;

            // Karşı tarafa “gördüm” bilgisi gönder
            socket.emit("messages_read", {
                reader: currentUser,
                sender: username
            });
        });
}


// Belirli bir grup sohbetini başlatır ve mesaj geçmişini yükler
function openGroupChat(groupName) {
    currentChatGroup = groupName;
    currentChatUser = null; // Özel sohbeti kapat
    const chatWindow = document.getElementById("chat-window");
    chatWindow.innerHTML = `<h2>${groupName} Sohbeti</h2>`;

    // Grup geçmişini getir
    fetch(`/api/messages/group/${groupName}`)
        .then(res => res.json())
        .then(messages => {
            messages.forEach(msg => {
                const p = document.createElement("p");
                const decrypted = decryptMessage(msg.message);
                p.innerText = `[${msg.sender} - ${msg.timestamp}]: ${decrypted}`;
                chatWindow.appendChild(p);
            });
            chatWindow.scrollTop = chatWindow.scrollHeight;
        });
}

// Grup listesine bir grup öğesi ekler (sahipse silme butonu ile)
function renderGroupItem(groupName, isOwner) {
    const groupList = document.getElementById("group-list");

    const div = document.createElement("div");
    div.className = "group-item";

    const span = document.createElement("span");
    span.textContent = groupName;
    span.style.flex = "1";
    span.onclick = () => openGroupChat(groupName);
    div.appendChild(span);

    if (isOwner) {
        const btn = document.createElement("button");
        btn.textContent = "❌";
        btn.style.marginLeft = "10px";
        btn.onclick = (e) => {
            e.stopPropagation();
            if (confirm(`Grubu '${groupName}' silmek istediğine emin misin?`)) {
                socket.emit("delete_group", { group_name: groupName });
            }
        };
        div.appendChild(btn);
    }

    groupList.appendChild(div);
}

// Mesaj gönderme işlemini yürütür
function sendMessage() {
    const messageInput = document.getElementById("message-input-field");
    const rawMessage = messageInput.value;
    if (rawMessage.trim() === "") return;

    const encryptedMessage = encryptMessage(rawMessage);

    const chatWindow = document.getElementById("chat-window");

    const p = document.createElement("p");
    p.className = "message-right";
    p.innerText = `[${currentUser}]: ${rawMessage}`; 
    chatWindow.appendChild(p);

    if (currentChatUser) {
        socket.emit("private_message", { to: currentChatUser, message: encryptedMessage });
    } else if (currentChatGroup) {
        socket.emit("group_message", { group: currentChatGroup, message: encryptedMessage });
    } else {
        alert("Sohbet etmek için bir kullanıcı veya grup seçin!");
    }

    messageInput.value = "";
    chatWindow.scrollTop = chatWindow.scrollHeight;
}



// Kullanıcının oturumunu kapatır
function logout() {
    sessionStorage.removeItem("username");
    sessionStorage.removeItem("token");
    window.location.href = "/";
}

// Grup oluşturma modalını açar ve aktif kullanıcıları doldurur
async function openCreateGroupModal() {
    document.getElementById("createGroupModal").style.display = "block";

    // Kullanıcıları getir
    const res = await fetch("/api/users/active");
    const data = await res.json();
    const container = document.getElementById("user-checkboxes");
    container.innerHTML = "";

    data.forEach(user => {
        if (user.username !== currentUser) {
            const label = document.createElement("label");
            label.style.display = "block";

            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.value = user.username;

            label.appendChild(checkbox);
            label.appendChild(document.createTextNode(" " + user.username));
            container.appendChild(label);
        }
    });
}

// Grup oluşturma modalını kapatır
function closeCreateGroupModal() {
    document.getElementById("createGroupModal").style.display = "none";
}

// Yeni bir grup oluşturma işlemini yürütür
function createGroup() {
    const groupName = document.getElementById("new-group-name").value.trim();
    const selectedUsers = Array.from(document.querySelectorAll("#user-checkboxes input:checked")).map(cb => cb.value);

    if (!groupName || selectedUsers.length === 0) {
        alert("Grup adı ve kullanıcı seçimi zorunlu!");
        return;
    }

    socket.emit("create_group", {
        group_name: groupName,
        members: selectedUsers
    });

    closeCreateGroupModal();
}

function openCallHistoryModal() {
  const modal = document.getElementById("callHistoryModal");
  const list = document.getElementById("call-history-list");
  modal.style.display = "block";
  list.innerHTML = "<li>Yükleniyor...</li>";

  fetch(`/api/call-log/${currentUser}`)
    .then(res => res.json())
    .then(data => {
      list.innerHTML = "";
      if (data.length === 0) {
        list.innerHTML = "<li>Hiç görüşme yapılmamış.</li>";
      } else {
        data.forEach(log => {
          const li = document.createElement("li");
          li.textContent = `${log.caller} → ${log.callee} (${log.duration} sn)`;
          list.appendChild(li);
        });
      }
    });
}

function closeCallHistoryModal() {
  document.getElementById("callHistoryModal").style.display = "none";
}


/* ================================================
🟢 SOCKET.IO OLAY DİNLEYİCİLERİ
================================================= */

// Soket bağlantısı kurulduğunda tetiklenir
socket.on('connect', () => {
    console.log('Socket.IO Bağlandı:', socket.id);
    // Bağlandığında mevcut kullanıcıyı tekrar kaydet
    if (currentUser) {
        socket.emit("register_socket", { username: currentUser });
    }
});

// Soket bağlantısı kesildiğinde tetiklenir
socket.on('disconnect', () => {
    console.log('Socket.IO Bağlantısı Kesildi');
});

// Genel mesaj alındığında tetiklenir (bu kodda aktif kullanımda değil)
socket.on('message', (data) => {
    console.log('Genel Mesaj:', data);
    const chatWindow = document.getElementById("chat-window");
    const p = document.createElement("p");
    p.innerText = `[Genel]: ${data.message}`;
    chatWindow.appendChild(p);
    chatWindow.scrollTop = chatWindow.scrollHeight;
});

// Özel mesaj alındığında tetiklenir
socket.on('private_message', (data) => {
    console.log('Özel Mesaj alındı:', data);
    const chatWindow = document.getElementById("chat-window");
    
    if (currentChatUser === data.from) {
        const p = document.createElement("p");
        p.className = "message-left";

        const decrypted = decryptMessage(data.message);

        p.innerText = `[${data.from}]: ${decrypted}`;
        chatWindow.appendChild(p);
        chatWindow.scrollTop = chatWindow.scrollHeight;
    } else {
        alert(`Yeni mesaj var: ${data.from}`);
    }
});


// Grup mesajı alındığında tetiklenir
socket.on('group_message', (data) => {
    console.log('Grup Mesajı alındı:', data);
    const chatWindow = document.getElementById("chat-window");

    if (currentChatGroup === data.group) {

        const p = document.createElement("p");
        const decrypted = decryptMessage(data.message);
        p.innerText = `[${data.group} - ${data.from}]: ${decrypted}`;
        chatWindow.appendChild(p);
        chatWindow.scrollTop = chatWindow.scrollHeight;
    } else {
        alert(`Yeni grup mesajı var: ${data.group} - ${data.from}`);
    }
});


// Bir grup silindiğinde tetiklenir
socket.on("group_deleted", (data) => {
    const groupList = document.getElementById("group-list");
    const items = groupList.getElementsByClassName("group-item");
    for (let i = 0; i < items.length; i++) {
        if (items[i].textContent.includes(data.group_name)) {
            groupList.removeChild(items[i]);
            break;
        }
    }

    // Açık sohbet o grubun sohbetiyse temizle
    if (currentChatGroup === data.group_name) {
        document.getElementById("chat-window").innerHTML = `<p>Bu grup silindi.</p>`;
    }
});

// Aktif kullanıcı listesi güncellendiğinde tetiklenir
socket.on('active_users_update', (data) => {
    console.log('Aktif kullanıcılar güncellendi:', data.users);
    updateUserList(data.users);
});

// Yeni bir grup oluşturulduğunda tetiklenir
socket.on('group_created', (data) => {
    console.log('Grup oluşturuldu:', data.group_name);
    alert(`'${data.group_name}' grubu oluşturuldu.`);

    const groupList = document.getElementById("group-list");
    const div = document.createElement("div");
    div.className = "group-item";
    div.textContent = data.group_name;
    div.onclick = () => openGroupChat(data.group_name);
    groupList.appendChild(div);

    // Gruba socket taraflı katılım
    socket.emit("join_group", { group: data.group_name });
});

// Kullanıcının üye olduğu grupları sunucudan çeker ve listeler
async function loadUserGroups() {
    try {
        const response = await fetch(`/api/groups/${currentUser}`);
        const groups = await response.json();

        const groupList = document.getElementById("group-list");
        groupList.innerHTML = ""; // Öncekileri temizle

        groups.forEach(group => {
            renderGroupItem(group.name, group.is_owner); // Grubu ve sahiplik bilgisini gönder
            socket.emit("join_group", { group: group.name }); // Odaya katıl
        });
    } catch (err) {
        console.error("Kullanıcının grupları alınamadı:", err);
    }
}

/* ================================================
🟢 WEBRTC FONKSİYONLARI VE OLAY DİNLEYİCİLERİ
================================================= */

// Sesli çağrıyı sonlandırır ve ilgili UI'ı sıfırlar
function endCall() {
    const callEnd = new Date();
        fetch("/api/call-log", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            caller: currentUser,
            callee: targetUser,
            start_time: callStart.toISOString().slice(0, 19).replace("T", " "),
            end_time: callEnd.toISOString().slice(0, 19).replace("T", " ")
        })
    });

    console.log("endCall fonksiyonu çağrıldı.");
    document.getElementById("voice-call-container").style.display = "none";
    document.getElementById("call-status").innerText = "";
    document.getElementById("remote-audio").srcObject = null;
    

    if (peerConnection) {
        peerConnection.close();
        peerConnection = null;
        console.log("PeerConnection kapatıldı.");
    }
    if (localStream) {
        localStream.getTracks().forEach(t => t.stop());
        localStream = null;
        console.log("Yerel ses akışı durduruldu.");
    }
    isCalling = false;
    isReceivingCall = false;
    targetUser = null;
    pendingCandidates = []; // Bekleyen adayları temizle
    // Arama butonlarını tekrar aktif hale getirme
    document.querySelectorAll('.call-button').forEach(btn => btn.style.display = 'block');
    document.getElementById('hangup-call-button').style.display = 'none';
    document.getElementById('call-accept-button').style.display = 'none';
    document.getElementById('call-reject-button').style.display = 'none';
}

// Belirli bir kullanıcıya sesli çağrı başlatır
async function startCall(user) {
    callStart = new Date(); 

    if (isCalling || isReceivingCall) {
        alert("Zaten bir arama devam ediyor veya alınıyor.");
        return;
    }

    // Önceki bir arama kalıntısı varsa temiz bir başlangıç için her şeyi kapat
    endCall();

    targetUser = user;
    isCalling = true;
    document.getElementById("voice-call-container").style.display = "block";
    document.getElementById("call-status").innerText = `${targetUser} aranıyor...`;
    document.getElementById("hangup-call-button").style.display = "block"; // Kapatma butonunu göster
    document.querySelectorAll('.call-button').forEach(btn => btn.style.display = 'none'); // Diğer arama butonlarını gizle

    try {
        // Yerel ses akışını al
        localStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        // Kendi sesinizi dinlemek için (isteğe bağlı, muted olduğu için genellikle rahatsız etmez)
        document.getElementById("local-audio").srcObject = localStream;

        // RTCPeerConnection oluştur ve STUN sunucusu ekle
        peerConnection = new RTCPeerConnection({
            iceServers: [
                { urls: 'stun:stun.l.google.com:19302' } // Google'ın genel STUN sunucusu
            ]
        });

        // Uzak akış geldiğinde
        peerConnection.ontrack = (event) => {
            console.log("Uzak ses akışı eklendi.", event.streams[0]);
            document.getElementById("remote-audio").srcObject = event.streams[0];
        };

        // ICE candidate'ler oluştuğunda
        peerConnection.onicecandidate = (event) => {
            if (event.candidate) {
                console.log("ICE adayı gönderiliyor:", event.candidate);
                socket.emit("ice-candidate", {
                    to: targetUser,
                    candidate: event.candidate
                });
            }
        };

        // Bağlantı durumu değiştiğinde
        peerConnection.onconnectionstatechange = (event) => {
            console.log("RTCPeerConnection durumu:", peerConnection.connectionState);
            switch (peerConnection.connectionState) {
                case "new":
                case "checking":
                    document.getElementById("call-status").innerText = "Bağlantı kontrol ediliyor...";
                    break;
                case "connected":
                    document.getElementById("call-status").innerText = `${targetUser} ile görüşüyorsun`;
                    // Bağlantı kurulduğunda arama butonlarını gizle, kapatma butonunu göster (tekrar emin olmak için)
                    document.getElementById("call-accept-button").style.display = "none";
                    document.getElementById("call-reject-button").style.display = "none";
                    document.getElementById("hangup-call-button").style.display = "block";
                    break;
                case "disconnected":
                case "failed":
                case "closed":
                    document.getElementById("call-status").innerText = "Arama sonlandı/Bağlantı hatası.";
                    endCall(); // Bağlantı kesildiğinde çağrıyı sonlandır
                    break;
            }
        };

        // Yerel ses akışını peer'e ekle
        localStream.getTracks().forEach(track => {
            peerConnection.addTrack(track, localStream);
            console.log("Yerel ses akışı peer'e eklendi.");
        });

        // Teklif oluştur ve gönder
        const offer = await peerConnection.createOffer();
        await peerConnection.setLocalDescription(offer);
        console.log("Teklif oluşturuldu ve yerel açıklama ayarlandı:", offer);

        socket.emit("call-offer", {
            to: targetUser,
            offer: offer
        });
        console.log("Arama teklifi gönderildi:", targetUser);

    } catch (error) {
        console.error("Arama başlatılırken hata oluştu:", error);
        document.getElementById("call-status").innerText = "Arama başlatılamadı: " + error.message;
        endCall(); // Hata durumunda çağrıyı sonlandır
    }
}

// Sunucudan gelen arama cevabını işler
socket.on("call-answer", async (data) => {
    console.log("Arama cevabı alındı:", data);
    if (!peerConnection) {
        console.warn("Arama cevabı geldi ama peerConnection oluşturulmadı.");
        return;
    }
    try {
        await peerConnection.setRemoteDescription(new RTCSessionDescription(data.answer));
        console.log("Uzak açıklama (cevap) ayarlandı.");
        // Bekleyen ICE adaylarını ekle
        while (pendingCandidates.length > 0) {
            const candidate = pendingCandidates.shift(); // İlk adayı al ve diziden çıkar
            try {
                if (peerConnection.remoteDescription && peerConnection.remoteDescription.type) {
                    await peerConnection.addIceCandidate(candidate);
                    console.log("Bekleyen ICE adayı eklendi:", candidate);
                } else {
                    console.warn("Bekleyen ICE adayı eklenemedi: Uzak açıklama henüz ayarlanmadı (cevap sonrası).");
                }
            } catch (err) {
                console.error("Bekleyen ICE adayı eklenirken hata (cevap sonrası):", err);
            }
        }
    } catch (error) {
        console.error("Arama cevabı işlenirken hata oluştu:", error);
        endCall(); // Hata durumunda çağrıyı sonlandır
    }
});

// Sunucudan gelen ICE adaylarını işler
socket.on("ice-candidate", async (data) => {
    console.log("ICE adayı alındı:", data.candidate);
    const candidate = new RTCIceCandidate(data.candidate);

    if (!peerConnection) {
        console.warn("ICE adayı geldi ama peerConnection oluşturulmadı, saklanıyor.");
        pendingCandidates.push(candidate);
        return;
    }

    // remoteDescription henüz ayarlanmadıysa adayı sakla
    if (!peerConnection.remoteDescription || peerConnection.remoteDescription.type === "") {
        console.warn("ICE adayı geldi ama remoteDescription hazır değil, saklanıyor.");
        pendingCandidates.push(candidate);
        return;
    }

    try {
        await peerConnection.addIceCandidate(candidate);
        console.log("ICE adayı eklendi.");
    } catch (err) {
        console.error("ICE adayı eklenemedi:", err);
    }
});

// Sunucudan gelen arama teklifini işler
socket.on("call-offer", async (data) => {
    console.log("Arama teklifi alındı:", data);
    if (isCalling || isReceivingCall) {
        console.warn("Zaten bir arama devam ediyor, yeni teklif reddediliyor.");
        socket.emit("call-rejected", { to: data.from, reason: "Busy" });
        return;
    }

    // Yeni bir arama teklifi geldiğinde önceki durumu temizle
    endCall();

    targetUser = data.from;
    isReceivingCall = true;
    document.getElementById("voice-call-container").style.display = "block";
    document.getElementById("call-status").innerText = `${targetUser} seni arıyor...`;
    document.getElementById("call-accept-button").style.display = "block";
    document.getElementById("call-reject-button").style.display = "block";
    document.getElementById("hangup-call-button").style.display = "none"; // Çağrıyı kapatma butonunu gizle
    document.querySelectorAll('.call-button').forEach(btn => btn.style.display = 'none'); // Diğer arama butonlarını gizle

    try {
        localStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        document.getElementById("local-audio").srcObject = localStream;

        peerConnection = new RTCPeerConnection({
            iceServers: [
                { urls: 'stun:stun.l.google.com:19302' }
            ]
        });

        peerConnection.ontrack = (event) => {
            console.log("Uzak ses akışı eklendi (gelen arama).", event.streams[0]);
            document.getElementById("remote-audio").srcObject = event.streams[0];
        };

        peerConnection.onicecandidate = (event) => {
            if (event.candidate) {
                console.log("ICE adayı gönderiliyor (gelen arama):", event.candidate);
                socket.emit("ice-candidate", {
                    to: targetUser,
                    candidate: event.candidate
                });
            }
        };

        peerConnection.onconnectionstatechange = (event) => {
            console.log("RTCPeerConnection durumu (gelen arama):", peerConnection.connectionState);
            switch (peerConnection.connectionState) {
                case "new":
                case "checking":
                    document.getElementById("call-status").innerText = "Bağlantı kontrol ediliyor...";
                    break;
                case "connected":
                    document.getElementById("call-status").innerText = `${targetUser} ile görüşüyorsun`;
                    // Bağlantı kurulduğunda butonları ayarla
                    document.getElementById("call-accept-button").style.display = "none";
                    document.getElementById("call-reject-button").style.display = "none";
                    document.getElementById("hangup-call-button").style.display = "block";
                    break;
                case "disconnected":
                case "failed":
                case "closed":
                    document.getElementById("call-status").innerText = "Arama sonlandı/Bağlantı hatası.";
                    endCall();
                    break;
            }
        };

        localStream.getTracks().forEach(track => {
            peerConnection.addTrack(track, localStream);
            console.log("Yerel ses akışı peer'e eklendi (gelen arama).");
        });

        await peerConnection.setRemoteDescription(new RTCSessionDescription(data.offer));
        console.log("Uzak açıklama (teklif) ayarlandı.");

        // Bekleyen ICE adaylarını ekle
        while (pendingCandidates.length > 0) {
            const candidate = pendingCandidates.shift(); // İlk adayı al ve diziden çıkar
            try {
                if (peerConnection.remoteDescription && peerConnection.remoteDescription.type) {
                    await peerConnection.addIceCandidate(candidate);
                    console.log("Bekleyen ICE adayı eklendi (gelen arama):", candidate);
                } else {
                    console.warn("Bekleyen ICE adayı eklenemedi (gelen arama): Uzak açıklama henüz ayarlanmadı.");
                }
            } catch (err) {
                console.error("Bekleyen ICE adayı eklenirken hata (gelen arama):", err);
            }
        }

    } catch (error) {
        console.error("Arama teklifi işlenirken hata oluştu:", error);
        document.getElementById("call-status").innerText = "Arama reddedildi: " + error.message;
        endCall(); // Hata durumunda çağrıyı sonlandır
        socket.emit("call-rejected", { to: data.from, reason: "Error handling offer" }); // Arayana hata bildir
    }
});

// Arama reddedildiğinde tetiklenir
socket.on("call-rejected", (data) => {
    console.log("Arama reddedildi:", data.from, data.reason);
    document.getElementById("call-status").innerText = `${data.from} aramayı ${data.reason === 'Busy' ? 'meşgul olduğu için' : 'reddedildi'}.`;
    setTimeout(() => {
        endCall();
    }, 3000); // 3 saniye sonra kapat
});

// Arama kabul etme butonu click eventi
document.getElementById("call-accept-button").addEventListener("click", async () => {
    console.log("Arama kabul edildi.");
    try {
        const answer = await peerConnection.createAnswer();
        await peerConnection.setLocalDescription(answer);
        console.log("Cevap oluşturuldu ve yerel açıklama ayarlandı:", answer);

        socket.emit("call-answer", {
            to: targetUser,
            answer: answer
        });
        document.getElementById("call-accept-button").style.display = "none";
        document.getElementById("call-reject-button").style.display = "none";
        document.getElementById("hangup-call-button").style.display = "block"; // Çağrıyı kapatma butonunu göster
    } catch (error) {
        console.error("Arama kabul edilirken hata oluştu:", error);
        document.getElementById("call-status").innerText = "Arama kabul edilemedi: " + error.message;
        endCall();
    }
});

// Arama reddetme butonu click eventi
document.getElementById("call-reject-button").addEventListener("click", () => {
    console.log("Arama reddedildi (kullanıcı tarafından).");
    socket.emit("call-rejected", { to: targetUser, reason: "Rejected by user" });
    document.getElementById("call-status").innerText = "Arama reddedildi.";
    endCall();
});

// Kapatma butonu click eventi
document.getElementById("hangup-call-button").addEventListener("click", () => {
    console.log("Arama kapatılıyor (kullanıcı tarafından).");
    socket.emit("call-ended", { to: targetUser }); // Karşı tarafa çağrının bittiğini bildir
    document.getElementById("call-status").innerText = "Arama sonlandı.";
    endCall();
});

// Karşı tarafın çağrıyı kapattığını gösteren olay
socket.on("call-ended", (data) => {
    console.log("Arama karşı taraf tarafından kapatıldı:", data.from);
    document.getElementById("call-status").innerText = `${data.from} aramayı sonlandırdı.`;
    setTimeout(() => {
        endCall();
    }, 2000); // Kısa bir gecikme ile çağrıyı sonlandır
});