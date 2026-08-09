self.addEventListener("push", (event) => {
  let data = { title: "Nouvelle notification", body: "" };
  try {
    data = event.data.json();
  } catch (e) {
    data.body = event.data ? event.data.text() : "";
  }

  const icon = data.icon || "icons/icon-192.png";

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon,
      badge: icon,
      tag: data.type || "general",
      data: { tab: data.type === "mail" ? "messagerie" : "notes" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const tab = event.notification.data && event.notification.data.tab;
  event.waitUntil(clients.openWindow(tab ? `/?tab=${tab}` : "/"));
});
