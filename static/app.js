function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)));
}

async function loadGrades() {
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
  loadGrades();
  document.getElementById("enable-push").addEventListener("click", enableNotifications);
  document.getElementById("refresh").addEventListener("click", loadGrades);
});
