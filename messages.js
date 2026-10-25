"use strict";
const loginForm = document.querySelector("#login-form");
const panel = document.querySelector("#messages-panel");
const statusBox = document.querySelector("#admin-status");
const list = document.querySelector("#messages-list");

function setStatus(text, success = false) {
  statusBox.textContent = text;
  statusBox.classList.toggle("success", success);
}

async function loadMessages() {
  const response = await fetch("/api/messages", { credentials: "same-origin" });
  if (response.status === 401) return false;
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Не вдалося отримати список.");
  list.replaceChildren();
  if (!data.messages.length) {
    const empty = document.createElement("p"); empty.className = "empty-state"; empty.textContent = "Поки що немає збережених повідомлень."; list.append(empty);
  }
  data.messages.forEach((message) => {
    const card = document.createElement("article"); card.className = "message-card";
    const header = document.createElement("header"); const details = document.createElement("div");
    const name = document.createElement("h3"); name.textContent = message.name;
    const email = document.createElement("a"); email.className = "message-email"; email.href = `mailto:${message.email}`; email.textContent = message.email;
    const date = document.createElement("time"); date.dateTime = message.created_at; date.textContent = new Date(message.created_at).toLocaleString("uk-UA");
    details.append(name, email); const remove = document.createElement("button"); remove.className = "delete-message"; remove.type = "button"; remove.textContent = "Видалити";
    remove.addEventListener("click", async () => {
      if (!window.confirm("Видалити це повідомлення?")) return;
      try {
        const result = await fetch(`/api/messages/${message.id}`, { method: "DELETE", credentials: "same-origin" });
        const body = await result.json(); if (!result.ok) throw new Error(body.error || "Не вдалося видалити повідомлення.");
        setStatus("Повідомлення видалено.", true); await loadMessages();
      } catch (error) { setStatus(error.message); }
    });
    header.append(details, date); const content = document.createElement("p"); content.textContent = message.message;
    card.append(header, content, remove); list.append(card);
  });
  loginForm.hidden = true; panel.hidden = false; setStatus("Вхід виконано.", true); return true;
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault(); setStatus("");
  const formData = new FormData(loginForm);
  try {
    const response = await fetch("/api/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.fromEntries(formData)) });
    const data = await response.json(); if (!response.ok) throw new Error(data.error || "Не вдалося увійти.");
    await loadMessages();
  } catch (error) { setStatus(error.message); }
});

document.querySelector("#logout-button").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  panel.hidden = true; loginForm.hidden = false; loginForm.reset(); setStatus("Ви вийшли з облікового запису.", true);
});

loadMessages().catch((error) => setStatus(error.message));
