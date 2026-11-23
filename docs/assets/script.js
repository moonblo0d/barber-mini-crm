// Адреса API для заявок. На GitHub Pages сервера немає — тоді форма працює в демо-режимі.
const API_URL = window.CRM_API_URL || "/api/leads";
const DEMO = location.hostname.endsWith("github.io") || location.protocol === "file:";

// ---------- Навігація ----------
const nav = document.getElementById("nav");
const burger = document.getElementById("burger");
const navLinks = document.getElementById("navLinks");

const onScroll = () => nav.classList.toggle("scrolled", window.scrollY > 20);
window.addEventListener("scroll", onScroll, { passive: true });
onScroll();

burger.addEventListener("click", () => {
  const open = navLinks.classList.toggle("open");
  burger.setAttribute("aria-expanded", String(open));
});
navLinks.querySelectorAll("a").forEach((a) =>
  a.addEventListener("click", () => {
    navLinks.classList.remove("open");
    burger.setAttribute("aria-expanded", "false");
  })
);

// ---------- Поява блоків при скролі ----------
const revealObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("visible");
        revealObserver.unobserve(entry.target);
      }
    });
  },
  { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
);
document.querySelectorAll(".reveal").forEach((el, i) => {
  el.style.transitionDelay = `${Math.min(i % 4, 3) * 80}ms`;
  revealObserver.observe(el);
});

// ---------- Лічильники в hero ----------
function animateCount(el) {
  const target = parseFloat(el.dataset.count);
  const decimals = el.dataset.count.includes(".") ? 1 : 0;
  const suffix = el.dataset.suffix || "";
  const start = performance.now();
  const duration = 1400;
  const step = (now) => {
    const p = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    const value = (target * eased).toFixed(decimals);
    el.textContent = Number(value).toLocaleString("uk-UA", { minimumFractionDigits: decimals }) + (p === 1 ? suffix : "");
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
const countObserver = new IntersectionObserver((entries) => {
  entries.forEach((e) => {
    if (e.isIntersecting) {
      animateCount(e.target);
      countObserver.unobserve(e.target);
    }
  });
});
document.querySelectorAll("[data-count]").forEach((el) => countObserver.observe(el));

// ---------- 3D-нахил карток (лише для миші) ----------
if (window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
  document.querySelectorAll(".tilt").forEach((card) => {
    card.addEventListener("mousemove", (e) => {
      const r = card.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - 0.5;
      const y = (e.clientY - r.top) / r.height - 0.5;
      card.style.transform = `perspective(800px) rotateX(${-y * 6}deg) rotateY(${x * 8}deg) translateY(-4px)`;
    });
    card.addEventListener("mouseleave", () => (card.style.transform = ""));
  });
}

// ---------- Форма запису ----------
const form = document.getElementById("leadForm");
const statusEl = document.getElementById("formStatus");
const submitBtn = document.getElementById("submitBtn");
const PHONE_RE = /^\+?[\d\s\-()]{9,18}$/;

function showErrors(errors) {
  form.querySelectorAll(".err").forEach((el) => {
    const field = el.dataset.for;
    el.textContent = errors[field] || "";
    form.elements[field].classList.toggle("invalid", Boolean(errors[field]));
  });
}

function validate(data) {
  const errors = {};
  if (!data.name || data.name.trim().length < 2) errors.name = "Вкажіть ім'я";
  if (!PHONE_RE.test((data.phone || "").trim())) errors.phone = "Вкажіть коректний номер";
  if (!data.service) errors.service = "Оберіть послугу";
  return errors;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(form));
  const errors = validate(data);
  showErrors(errors);
  statusEl.className = "form-status";
  statusEl.textContent = "";
  if (Object.keys(errors).length) return;

  submitBtn.disabled = true;
  submitBtn.textContent = "Надсилаємо…";
  try {
    if (DEMO) {
      await new Promise((r) => setTimeout(r, 700));
      statusEl.className = "form-status ok";
      statusEl.textContent = "Демо-режим: у робочій версії заявка потрапляє в CRM і майстру в Telegram ✅";
      form.reset();
      return;
    }
    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    const body = await res.json().catch(() => ({}));
    if (res.ok && body.ok) {
      statusEl.className = "form-status ok";
      statusEl.textContent = "Дякуємо! Заявку прийнято — майстер напише вам найближчим часом ✅";
      form.reset();
    } else if (body.errors) {
      showErrors(body.errors);
    } else {
      throw new Error(body.error || "Помилка сервера");
    }
  } catch (err) {
    statusEl.className = "form-status fail";
    statusEl.textContent = "Не вдалося надіслати. Спробуйте ще раз або напишіть нам у Telegram.";
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Надіслати заявку";
  }
});
