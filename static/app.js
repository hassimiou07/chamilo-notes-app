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

async function loadFiche() {
  const res = await fetch("/api/fiche");
  const fiche = await res.json();
  const info = document.getElementById("semestre-info");
  const container = document.getElementById("modules-list");
  container.innerHTML = "";

  if (!fiche || !fiche.modules || !fiche.modules.length) {
    info.textContent = "";
    return;
  }

  const enAttente = fiche.modules.filter((m) => m.note_attendue).length;
  info.textContent =
    `BUT ${fiche.annee}A · Semestre ${fiche.semestre} — ${fiche.modules.length} modules, ` +
    `${enAttente} sans note pour l'instant`;

  const titre = document.createElement("h2");
  titre.className = "section-titre";
  titre.textContent = "Modules du semestre";
  container.appendChild(titre);

  for (const m of fiche.modules) {
    const card = document.createElement("div");
    card.className = "card module" + (m.note_attendue ? " en-attente" : "");
    const chips = Object.entries(m.ue || {})
      .map(([nom, coef]) => `<span class="ue-chip">${nom}<b>${coef}</b></span>`)
      .join("");
    card.innerHTML = `
      <h3>${m.code} <span class="module-nom">${m.nom}</span></h3>
      <p class="statut">${
        m.note_attendue ? "épreuve·s à venir" : `moyenne ${m.moyenne || "—"}`
      }</p>
      <div class="ue-chips">${chips}</div>
    `;
    container.appendChild(card);
  }
}

async function loadGrades() {
  await loadUeAverages();
  await loadFiche();
  const res = await fetch("/api/grades");
  const { grades } = await res.json();
  const list = document.getElementById("grades-list");
  list.innerHTML = "";

  if (!grades.length) {
    list.innerHTML =
      "<p class='empty'>Aucune note tombée dans ce semestre pour l'instant.</p>";
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

const TAB_TITLES = {
  notes: "Mes Notes",
  messagerie: "Ma Messagerie",
  planning: "Ma Semaine",
};

function setupTabs() {
  const tabs = document.querySelectorAll(".tab");
  const title = document.getElementById("page-title");
  tabs.forEach((tab) => {
    tab.addEventListener("click", async () => {
      const nom = tab.dataset.tab;
      tabs.forEach((t) => t.classList.toggle("active", t === tab));
      document.querySelectorAll("section[id^='tab-']").forEach((section) => {
        section.hidden = section.id !== `tab-${nom}`;
      });
      title.textContent = TAB_TITLES[nom] || "";

      // Synchroniser / Actualiser ne concernent que les donnees Chamilo.
      document.getElementById("sync").hidden = nom === "planning";
      document.getElementById("refresh").hidden = nom === "planning";

      if (!loadedTabs.has(nom)) {
        loadedTabs.add(nom);
        if (nom === "messagerie") {
          await loadMessages();
        } else if (nom === "planning") {
          const frame = document.getElementById("planning-frame");
          frame.src = frame.dataset.src;
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
  // Un echec d'enregistrement ne doit pas empecher l'app de s'afficher :
  // sans try/catch, l'exception interrompait tout le reste du chargement
  // (onglets, notes, planning) et la page restait vide.
  if ("serviceWorker" in navigator) {
    try {
      await navigator.serviceWorker.register("/service-worker.js");
    } catch (err) {
      console.warn("Service worker non enregistre (hors ligne indisponible) :", err);
    }
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
