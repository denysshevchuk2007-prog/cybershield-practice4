"use strict";

const menuButton = document.querySelector(".menu-toggle");
const nav = document.querySelector("#main-nav");
const themeButton = document.querySelector(".theme-toggle");

menuButton.addEventListener("click", () => {
  const isOpen = menuButton.getAttribute("aria-expanded") === "true";
  menuButton.setAttribute("aria-expanded", String(!isOpen));
  menuButton.setAttribute("aria-label", isOpen ? "Відкрити меню" : "Закрити меню");
  nav.classList.toggle("is-open", !isOpen);
});

nav.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => {
  menuButton.setAttribute("aria-expanded", "false");
  menuButton.setAttribute("aria-label", "Відкрити меню");
  nav.classList.remove("is-open");
}));

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const isDark = theme === "dark";
  themeButton.setAttribute("aria-label", isDark ? "Увімкнути світлу тему" : "Увімкнути темну тему");
  themeButton.querySelector("span").textContent = isDark ? "☼" : "☾";
  localStorage.setItem("cybershield-theme", theme);
}

setTheme(localStorage.getItem("cybershield-theme") || "dark");
themeButton.addEventListener("click", () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));

function wireDisclosure(buttonSelector, contentSelector) {
  const button = document.querySelector(buttonSelector);
  const content = document.querySelector(contentSelector);
  button.addEventListener("click", () => {
    const expanded = button.getAttribute("aria-expanded") === "true";
    button.setAttribute("aria-expanded", String(!expanded));
    content.hidden = expanded;
    const marker = button.querySelector("span");
    if (marker) marker.textContent = expanded ? "＋" : "−";
  });
}

wireDisclosure(".reveal-button", "#hero-extra");
wireDisclosure(".learn-button", "#about-extra");

const services = [
  { icon: "⌘", title: "Захист акаунтів", description: "Створюй унікальні паролі та використовуй багатофакторну автентифікацію.", link: "https://www.cisa.gov/secure-our-world/use-strong-passwords" },
  { icon: "◉", title: "Захист від фішингу", description: "Навчися розпізнавати підозрілі повідомлення, посилання та вкладення.", link: "https://www.cisa.gov/secure-our-world/recognize-and-report-phishing" },
  { icon: "▣", title: "Резервні копії", description: "Зберігай важливі файли у резервних копіях, щоб не втратити їх.", link: "https://www.cisa.gov/secure-our-world" }
];
const serviceGrid = document.querySelector("#service-grid");

function renderServices() {
  serviceGrid.replaceChildren();
  services.forEach((service, index) => {
    const card = document.createElement("article");
    card.className = "service-card";
    const icon = document.createElement("div"); icon.className = "service-icon"; icon.textContent = service.icon;
    const title = document.createElement("h3"); title.textContent = service.title;
    const description = document.createElement("p"); description.textContent = service.description;
    const link = document.createElement("a"); link.href = service.link; link.target = "_blank"; link.rel = "noopener noreferrer"; link.append("Дізнатися більше ");
    const arrow = document.createElement("span"); arrow.textContent = "↗"; link.append(arrow);
    const remove = document.createElement("button"); remove.className = "remove-item"; remove.type = "button"; remove.textContent = "Видалити"; remove.setAttribute("aria-label", `Видалити: ${service.title}`);
    remove.addEventListener("click", () => { services.splice(index, 1); renderServices(); });
    card.append(icon, title, description, link, remove); serviceGrid.append(card);
  });
}
renderServices();

document.querySelector("#add-tip-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = document.querySelector("#tip-title");
  const title = input.value.trim();
  if (!title) { input.focus(); return; }
  services.push({ icon: "✦", title, description: "Нова порада додана до цього списку. Практикуй безпечні цифрові звички щодня.", link: "https://www.cisa.gov/secure-our-world" });
  renderServices(); event.currentTarget.reset(); input.focus();
});

const tips = [
  ["Перевіряй посилання", "Перш ніж натиснути, перевір адресу сайту та відправника."],
  ["Оновлюй програми", "Оновлення часто усувають відомі вразливості."],
  ["Не ділися зайвим", "Публікуй лише ту особисту інформацію, яка справді потрібна."]
];
const tipsList = document.querySelector("#tips-list");
tips.forEach(([title, description]) => {
  const item = document.createElement("li"); const mark = document.createElement("span"); mark.textContent = "✓";
  const content = document.createElement("div"); const heading = document.createElement("strong"); heading.textContent = title;
  const detail = document.createElement("p"); detail.textContent = description; content.append(heading, detail); item.append(mark, content); tipsList.append(item);
});

const form = document.querySelector("#contact-form");
const status = document.querySelector("#form-status");
const rules = {
  name: (value) => value.trim().length >= 2 ? "" : "Вкажи ім’я (не менше 2 символів).",
  email: (value) => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value.trim()) ? "" : "Введи коректну електронну адресу.",
  message: (value) => value.trim().length >= 5 ? "" : "Повідомлення має містити щонайменше 5 символів."
};

function validateField(field) {
  const error = rules[field.name](field.value);
  document.querySelector(`#${field.name}-error`).textContent = error;
  field.setAttribute("aria-invalid", String(Boolean(error)));
  return !error;
}

form.querySelectorAll("input, textarea").forEach((field) => field.addEventListener("input", () => {
  validateField(field); status.textContent = ""; status.classList.remove("success");
}));

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const fields = [...form.querySelectorAll("input, textarea")];
  const valid = fields.map(validateField).every(Boolean);
  if (!valid) {
    status.textContent = "Перевір поля з помилками та спробуй ще раз."; status.classList.remove("success");
    fields.find((field) => field.getAttribute("aria-invalid") === "true")?.focus(); return;
  }
  const submitButton = form.querySelector("[type=submit]");
  submitButton.disabled = true;
  status.textContent = "Надсилаємо повідомлення…";
  status.classList.remove("success");
  fetch(form.action, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Accept": "application/json" },
    body: JSON.stringify(Object.fromEntries(new FormData(form)))
  }).then(async (response) => {
    const result = await response.json();
    if (!response.ok) {
      Object.entries(result.fields || {}).forEach(([fieldName, message]) => {
        const field = form.elements.namedItem(fieldName);
        document.querySelector(`#${fieldName}-error`).textContent = message;
        field.setAttribute("aria-invalid", "true");
      });
      throw new Error(result.error || "Не вдалося зберегти повідомлення.");
    }
    status.textContent = result.message || "Повідомлення успішно збережено.";
    status.classList.add("success"); form.reset();
    fields.forEach((field) => { field.removeAttribute("aria-invalid"); document.querySelector(`#${field.name}-error`).textContent = ""; });
  }).catch((error) => {
    status.textContent = error instanceof TypeError ? "Не вдалося з’єднатися із сервером. Перевір, чи він запущений." : error.message;
    status.classList.remove("success");
  }).finally(() => { submitButton.disabled = false; });
});
