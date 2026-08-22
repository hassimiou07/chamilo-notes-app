function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)));
}

function ueColor(moyenneStr) {
  const val = parseFloat(moyenneStr.replace(",", "."));
  if (isNaN(val)) return "";
  if (val < 8) return "ue-red";
  if (val < 10) return "ue-orange";
  return "ue-green";
}

async function loadUeAverages() {
  const res = await fetch("/api/ue-averages");
  const { ue_averages } = await res.json();
  const container = document.getElementById("ue-table");
  container.innerHTML = "";

  if (!ue_averages.length) return;

  const table = document.createElement("div");
  table.className = "ue-grid";
  for (const ue of ue_averages) {
    const cell = document.createElement("div");
    cell.className = "ue-cell " + ueColor(ue.moyenne);
    cell.innerHTML = `<span class="ue-nom">${ue.nom}</span><span class="ue-moy">${ue.moyenne}</span>`;
    table.appendChild(cell);
  }
  container.appendChild(table);
}

async function loadGrades() {
  await loadUeAverages();
  const res = await fetch("/api/grades");
  const { grades } = await res.json();
  const list = document.getElementById("grades-list");
  list.innerHTML = "";

  if (!grades.length) {
    list.innerHTML = "<p class='empty'>Aucune note pour le moment.</p>";
    return;
  }

  for (const g of grades) {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <h3>${g.matiere}</h3>
      <p class="epreuve">${g.epreuve}</p>
      <div class="row">
        <span class="note">${g.note}<span class="over20">/20</span></span>
        <span class="coef">coef ${g.coef}</span>
      </div>
      <p class="moyenne">Ta moyenne dans cette ressource : ${g.moyenne}</p>
    `;
    list.appendChild(card);
  }
}

let currentMessages = [];

async function loadMessages() {
  const res = await fetch("/api/messages");
  const { messages } = await res.json();
  currentMessages = messages;
  const list = document.getElementById("messages-list");
  list.innerHTML = "";

  if (!messages.length) {
    list.innerHTML = "<p class='empty'>Aucun message pour le moment.</p>";
    return;
  }

  messages.forEach((m, idx) => {
    const card = document.createElement("div");
    card.className = "card mail-card" + (m.unread ? " unread" : "");
    card.dataset.idx = idx;
    const date = m.date ? new Date(m.date).toLocaleString("fr-FR") : "";
    card.innerHTML = `
      <h3>${m.unread ? '<span class="dot"></span>' : ""}${m.subject}</h3>
      <p class="epreuve">${m.from}</p>
      <p class="moyenne">${date}</p>
    `;
    card.addEventListener("click", () => openMessage(idx));
    list.appendChild(card);
  });
}

async function openMessage(idx) {
  const m = currentMessages[idx];
  document.getElementById("detail-subject").textContent = m.subject;
  document.getElementById("detail-from").textContent = m.from;
  document.getElementById("detail-date").textContent = m.date
    ? new Date(m.date).toLocaleString("fr-FR")
    : "";
  document.getElementById("detail-body").textContent = m.body;
  document.getElementById("message-detail").hidden = false;

  if (m.unread) {
    m.unread = false;
    const card = document.querySelector(`.mail-card[data-idx="${idx}"]`);
    if (card) {
      card.classList.remove("unread");
      const dot = card.querySelector(".dot");
      if (dot) dot.remove();
    }
    fetch("/api/messages/read", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: m.id }),
    });
  }
}

const loadedTabs = new Set();

function setupTabs() {
  const tabs = document.querySelectorAll(".tab");
  const title = document.getElementById("page-title");
  tabs.forEach((tab) => {
    tab.addEventListener("click", async () => {
      tabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById("tab-notes").hidden = tab.dataset.tab !== "notes";
      document.getElementById("tab-messagerie").hidden = tab.dataset.tab !== "messagerie";
      title.textContent = tab.dataset.tab === "notes" ? "Mes Notes" : "Ma Messagerie";

      if (!loadedTabs.has(tab.dataset.tab)) {
        loadedTabs.add(tab.dataset.tab);
        if (tab.dataset.tab === "messagerie") {
          await loadMessages();
        }
      }
    });
  });
}

async function refreshCurrentTab() {
  const activeTab = document.querySelector(".tab.active").dataset.tab;
  if (activeTab === "notes") {
    await loadGrades();
  } else {
    await loadMessages();
  }
}

async function syncNow() {
  const btn = document.getElementById("sync");
  const status = document.getElementById("sync-status");
  btn.disabled = true;
  status.textContent = "Synchronisation en cours (le serveur peut mettre jusqu'a 1 min a se reveiller)...";

  try {
    const res = await fetch("/api/sync", { method: "POST" });
    if (!res.ok) throw new Error("Echec de la synchronisation");
    const data = await res.json();
    await refreshCurrentTab();
    status.textContent = `Synchronise : ${data.new_grades} nouvelle(s) note(s), ${data.new_messages} nouveau(x) message(s).`;
  } catch (err) {
    status.textContent = "Erreur lors de la synchronisation. Reessaie dans quelques secondes.";
  } finally {
    btn.disabled = false;
  }
}

async function enableNotifications() {
  const status = document.getElementById("push-status");
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    status.textContent = "Les notifications push ne sont pas supportees sur ce navigateur.";
    return;
  }

  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    status.textContent = "Permission refusee.";
    return;
  }

  const reg = await navigator.serviceWorker.ready;
  const { publicKey } = await (await fetch("/api/vapid-public-key")).json();

  const subscription = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(publicKey),
  });

  await fetch("/api/subscribe", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(subscription),
  });

  status.textContent = "Notifications activees !";
}

window.addEventListener("load", async () => {
  if ("serviceWorker" in navigator) {
    await navigator.serviceWorker.register("/service-worker.js");
  }
  setupTabs();
  loadedTabs.add("notes");
  loadGrades();
  document.getElementById("enable-push").addEventListener("click", enableNotifications);
  document.getElementById("refresh").addEventListener("click", refreshCurrentTab);
  document.getElementById("sync").addEventListener("click", syncNow);
  document.getElementById("close-detail").addEventListener("click", () => {
    document.getElementById("message-detail").hidden = true;
  });
  setupSwipeToClose();

  const requestedTab = new URLSearchParams(location.search).get("tab");
  if (requestedTab === "messagerie") {
    document.querySelector('[data-tab="messagerie"]').click();
  }
});

function setupSwipeToClose() {
  const overlay = document.getElementById("message-detail");
  let startX = 0;
  let startY = 0;

  overlay.addEventListener("touchstart", (e) => {
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
  }, { passive: true });

  overlay.addEventListener("touchend", (e) => {
    const endX = e.changedTouches[0].clientX;
    const endY = e.changedTouches[0].clientY;
    const deltaX = endX - startX;
    const deltaY = Math.abs(endY - startY);

    if (deltaX > 70 && deltaY < 80) {
      overlay.hidden = true;
    }
  }, { passive: true });
}
