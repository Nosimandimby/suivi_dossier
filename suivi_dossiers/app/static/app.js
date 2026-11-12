/* Suivi des dossiers - application mono-page en JavaScript simple (sans framework) */

"use strict";

const TOKEN_KEY = "dossiertrack_token";
const USERS_PATH = "#/users";

/* Préfixe du chemin où l'application est servie.  Sous Home Assistant, la page
   vit dans /api/hassio_ingress/<jeton>/ : les appels API doivent donc être
   relatifs et conserver ce préfixe (les URL absolues /api/... pointeraient
   vers Home Assistant).  En local, le préfixe vaut simplement "/". */
const BASE_PATH = (() => {
  const chemin = window.location.pathname || "/";
  return chemin.endsWith("/") ? chemin : chemin.slice(0, chemin.lastIndexOf("/") + 1);
})();

function apiUrl(chemin) {
  return BASE_PATH + String(chemin).replace(/^\/+/, "");
}

const state = {
  token: localStorage.getItem(TOKEN_KEY),
  user: null,
  meta: null,
  filters: { q: "", type: "", state: "", status: "", verifier_id: "" },
  usersEditId: null,
};

/* ------------------------------------------------------------------ */
/* Outils                                                             */
/* ------------------------------------------------------------------ */

/* Texte comparable pour la recherche : minuscules, sans accents. */
function fold(value) {
  return String(value == null ? "" : value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function esc(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, (ch) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]
  );
}

function fmtDate(value) {
  if (!value) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/.exec(String(value));
  if (m) {
    const date = `${m[3]}/${m[2]}/${m[1]}`;
    return m[4] ? `${date} ${m[4]}:${m[5]}` : date;
  }
  return String(value);
}

function todayIso() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/* Classe CSS sûre pour un état ou un statut accentué / avec espaces. */
function slug(value) {
  return String(value == null ? "" : value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function statusBadge(status) {
  const key = status === "Visé" ? "vise" : slug(status);
  return `<span class="badge badge-${key}">${esc(status)}</span>`;
}

function stateBadge(value) {
  return `<span class="badge badge-${slug(value)}">${esc(value)}</span>`;
}

/* Petit panneau flottant, ancré au bouton qui l'ouvre et jamais coupé par le
   bas de la fenêtre (bascule au-dessus du bouton si nécessaire). */
let activePopover = null;

function positionPopover(panel, anchor) {
  const margin = 8;
  const rect = anchor.getBoundingClientRect();
  const width = panel.offsetWidth;
  const height = panel.offsetHeight;
  const left = Math.max(
    margin,
    Math.min(rect.left, window.innerWidth - width - margin)
  );
  let top = rect.bottom + margin;
  if (top + height > window.innerHeight - margin) {
    const above = rect.top - height - margin;
    top = above >= margin ? above : Math.max(margin, window.innerHeight - height - margin);
  }
  panel.style.left = `${Math.round(left)}px`;
  panel.style.top = `${Math.round(top)}px`;
}

function closePopovers() {
  if (!activePopover) return;
  activePopover.panel.hidden = true;
  activePopover = null;
}

function openPopover(panel, anchor) {
  const wasOpen = activePopover && activePopover.panel === panel;
  closePopovers();
  if (wasOpen) return;
  panel.hidden = false;
  activePopover = { panel, anchor };
  positionPopover(panel, anchor);
  const first = panel.querySelector("input:not([readonly]), select, textarea");
  if (first) first.focus();
}

document.addEventListener("click", (event) => {
  if (!activePopover) return;
  if (
    activePopover.panel.contains(event.target) ||
    activePopover.anchor.contains(event.target)
  )
    return;
  closePopovers();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closePopovers();
});

for (const target of [window, document]) {
  target.addEventListener(
    "scroll",
    () => {
      if (activePopover) positionPopover(activePopover.panel, activePopover.anchor);
    },
    true
  );
}

window.addEventListener("resize", () => {
  if (activePopover) positionPopover(activePopover.panel, activePopover.anchor);
});

function typeLabel(type) {
  const types = (state.meta && state.meta.types) || [];
  const found = types.find((t) => t.value === type);
  return found ? found.label : type;
}

function typeBadge(type) {
  return `<span class="badge badge-type">${esc(typeLabel(type))}</span>`;
}

function typeRangeLabel(t) {
  if (t.next === null) return "plage épuisée";
  return t.end == null ? `${t.start} et suivants` : `${t.start} – ${t.end}`;
}

function detailMessage(data, res) {
  if (data && data.detail != null) {
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail.map((d) => d.msg || JSON.stringify(d)).join(" ; ");
    }
    return JSON.stringify(data.detail);
  }
  return `Échec de la requête (${res.status})`;
}

function clearSession() {
  state.token = null;
  state.user = null;
  state.meta = null;
  localStorage.removeItem(TOKEN_KEY);
}

async function api(path, options = {}) {
  const method = options.method || "GET";
  const hadToken = !!state.token;
  const headers = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (state.token) headers["Authorization"] = "Bearer " + state.token;

  let res;
  try {
    res = await fetch(apiUrl(path), {
      method,
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch (err) {
    throw new Error("Impossible de joindre le serveur. Est-il toujours démarré ?");
  }

  let data = null;
  try {
    data = await res.json();
  } catch (err) {
    /* corps vide */
  }

  if (res.status === 401 && hadToken && path !== "/api/login") {
    clearSession();
    route("Votre session a expiré. Veuillez vous reconnecter.");
    throw new Error("Session expirée");
  }
  if (!res.ok) throw new Error(detailMessage(data, res));
  return data;
}

function showAppChrome() {
  const topbar = document.getElementById("topbar");
  topbar.hidden = false;
  document.getElementById("current-user").textContent = state.user
    ? state.user.display_name
    : "";
}

function setActiveNav(name) {
  document.querySelectorAll(".main-nav a[data-nav]").forEach((a) => {
    a.classList.toggle("active", a.dataset.nav === name);
  });
}

function renderError(err) {
  document.getElementById("app").innerHTML =
    `<div class="error">${esc(err && err.message ? err.message : String(err))}</div>`;
}

/* ------------------------------------------------------------------ */
/* Authentification                                                   */
/* ------------------------------------------------------------------ */

function renderLogin(message, kind) {
  document.getElementById("topbar").hidden = true;
  document.getElementById("app").innerHTML = `
    <div class="auth-wrap">
      <form class="card auth-card" id="login-form">
        <h1>Suivi des dossiers</h1>
        <p class="muted">Connectez-vous pour continuer</p>
        ${
          message
            ? `<div class="${kind === "notice" ? "notice" : "error"}">${esc(message)}</div>`
            : ""
        }
        <div class="field">
          <label for="login-identity">Identifiant</label>
          <input id="login-identity" name="identity" autocomplete="username" required>
        </div>
        <div class="field">
          <label for="login-password">Mot de passe</label>
          <input id="login-password" name="password" type="password" autocomplete="current-password" required>
        </div>
        <div class="error" id="login-error" hidden></div>
        <button class="btn btn-primary btn-block" type="submit">Se connecter</button>
        <p class="hint">Compte de démonstration : <code>admin</code> / <code>admin</code></p>
      </form>
    </div>`;

  document.getElementById("login-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const form = ev.target;
    const button = form.querySelector("button[type=submit]");
    const errorBox = document.getElementById("login-error");
    errorBox.hidden = true;
    button.disabled = true;
    try {
      const data = await api("/api/login", {
        method: "POST",
        body: {
          identity: form.elements.identity.value.trim(),
          password: form.elements.password.value,
        },
      });
      state.token = data.token;
      state.user = data.user;
      localStorage.setItem(TOKEN_KEY, data.token);
      state.meta = await api("/api/meta");
      if (!location.hash || location.hash === "#/") route();
      else location.hash = "#/";
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.hidden = false;
      button.disabled = false;
    }
  });
}

async function signOut() {
  try {
    await api("/api/logout", { method: "POST" });
  } catch (err) {
    /* ignoré - la session est effacée localement de toute façon */
  }
  clearSession();
  location.hash = "";
  route();
}

/* ------------------------------------------------------------------ */
/* Tableau de bord                                                    */
/* ------------------------------------------------------------------ */

function activityItem(item) {
  const dotClass =
    item.kind === "remark"
      ? "is-remark"
      : item.kind === "withdrawn"
      ? "is-withdrawn"
      : "";
  const link = `<a href="#/dossiers/${item.dossier_id}"><span class="activity-ref">${esc(
    item.reference_number
  )}</span></a>`;
  let body;
  if (item.kind === "remark") {
    body = `<strong>${esc(item.who)}</strong> a commenté ${link}<div class="small muted">${esc(
      item.text
    )}</div>`;
  } else if (item.kind === "withdrawn") {
    body = `<strong>${esc(item.who)}</strong> a retiré ${link} <span class="muted">${esc(
      item.name
    )}</span>`;
  } else {
    body = `<strong>${esc(item.who)}</strong> a créé ${link} <span class="muted">${esc(
      item.name
    )}</span>`;
  }
  return `<li>
      <span class="activity-dot ${dotClass}"></span>
      <div class="activity-body">${body}</div>
      <span class="activity-time">${esc(fmtDate(item.at))}</span>
    </li>`;
}

async function renderDashboard() {
  setActiveNav("dashboard");
  const app = document.getElementById("app");
  app.innerHTML = `<div class="page-head"><h1>Tableau de bord</h1></div><p class="muted">Chargement…</p>`;
  try {
    const data = await api("/api/dashboard");
    const byStatus = data.by_status;
    const statuses = state.meta.statuses;
    const statusCards = statuses
      .map((s) => {
        const k = s === "Visé" ? "vise" : slug(s);
        const cls =
          k === "vise" ? "is-green" : k === "rejete" ? "is-red" : k === "en-cours" ? "is-amber" : "";
        return `<div class="stat ${cls}">
            <div class="stat-value">${byStatus[s] || 0}</div>
            <div class="stat-label">${esc(s)}</div>
          </div>`;
      })
      .join("");

    const matrixRows = data.counts
      .map((row) => {
        const cells = statuses
          .map((s) => `<td class="num">${row.counts[s] || 0}</td>`)
          .join("");
        return `<tr>
            <td>${typeBadge(row.type)}</td>
            ${cells}
            <td class="num"><strong>${row.total}</strong></td>
          </tr>`;
      })
      .join("");

    const footCells = statuses
      .map((s) => `<td class="num">${byStatus[s] || 0}</td>`)
      .join("");

    const activity = data.activity.length
      ? data.activity.map(activityItem).join("")
      : `<li class="empty">Aucune activité pour le moment. Créez votre premier dossier.</li>`;

    app.innerHTML = `
      <div class="page-head"><h1>Tableau de bord</h1></div>
      <div class="stat-row">
        <div class="stat"><div class="stat-value">${data.total}</div><div class="stat-label">Total des dossiers</div></div>
        ${statusCards}
      </div>

      <section class="card">
        <h2>Répartition par type et statut</h2>
        <div class="table-wrap">
          <table class="data">
            <thead>
              <tr>
                <th>Type</th>
                ${statuses.map((s) => `<th class="num">${esc(s)}</th>`).join("")}
                <th class="num">Total</th>
              </tr>
            </thead>
            <tbody>${matrixRows || `<tr><td colspan="${statuses.length + 2}" class="empty">Aucun dossier pour le moment.</td></tr>`}</tbody>
            <tfoot>
              <tr>
                <td>Tous les types</td>
                ${footCells}
                <td class="num">${data.total}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </section>

      <section class="card">
        <h2>Activité récente</h2>
        <ul class="activity-list">${activity}</ul>
      </section>`;
  } catch (err) {
    if (err.message !== "Session expirée") renderError(err);
  }
}

/* ------------------------------------------------------------------ */
/* Liste des dossiers                                                 */
/* ------------------------------------------------------------------ */

async function renderList() {
  setActiveNav("dossiers");
  const app = document.getElementById("app");
  app.innerHTML = `<div class="page-head"><h1>Dossiers</h1></div><p class="muted">Chargement…</p>`;
  try {
    const [users, dossiers] = await Promise.all([
      api("/api/users"),
      api("/api/dossiers" + buildFilterQuery()),
    ]);

    const typeOptions = ["", ...state.meta.types.map((t) => t.value)]
      .map(
        (v) =>
          `<option value="${esc(v)}" ${state.filters.type === v ? "selected" : ""}>${
            v ? esc(typeLabel(v)) : "Tous les types"
          }</option>`
      )
      .join("");
    const stateOptions = ["", ...state.meta.states]
      .map(
        (v) =>
          `<option value="${esc(v)}" ${state.filters.state === v ? "selected" : ""}>${
            v ? esc(v) : "Tous les états"
          }</option>`
      )
      .join("");
    const statusOptions = ["", ...state.meta.statuses]
      .map(
        (v) =>
          `<option value="${esc(v)}" ${state.filters.status === v ? "selected" : ""}>${
            v ? esc(v) : "Tous les statuts"
          }</option>`
      )
      .join("");
    const verifierOptions = users
      .map(
        (u) =>
          `<option value="${u.id}" ${
            String(state.filters.verifier_id) === String(u.id) ? "selected" : ""
          }> ${esc(u.display_name)}</option>`
      )
      .join("");

    const rows = dossiers
      .map(
        (d) => `<tr class="hoverable" data-id="${d.id}">
            <td class="ref">${esc(d.reference_number)}</td>
            <td><a href="#/dossiers/${d.id}">${esc(d.name)}</a></td>
            <td>${typeBadge(d.type)}</td>
            <td>${stateBadge(d.state)}</td>
            <td>${statusBadge(d.status)}</td>
            <td>${esc(d.verifier_name)}</td>
            <td>${esc(fmtDate(d.created_date))}</td>
            <td>${esc(fmtDate(d.withdrawal_date))}</td>
            <td>
              <div class="row-actions">
                <button class="btn btn-sm btn-danger" data-del-dossier="${d.id}" type="button">Supprimer</button>
              </div>
            </td>
          </tr>`
      )
      .join("");

    app.innerHTML = `
      <div class="page-head">
        <h1>Dossiers</h1>
        <a class="btn btn-primary" href="#/dossiers/new">+ Nouveau dossier</a>
      </div>

      <div class="card">
        <div class="filters">
          <div class="field field-search">
            <label for="f-q">Recherche</label>
            <input id="f-q" type="search" placeholder="Référence, nom, type, vérificateur…"
                   value="${esc(state.filters.q)}" autocomplete="off">
          </div>
          <div class="field">
            <label for="f-type">Type</label>
            <select id="f-type">${typeOptions}</select>
          </div>
          <div class="field">
            <label for="f-state">État</label>
            <select id="f-state">${stateOptions}</select>
          </div>
          <div class="field">
            <label for="f-status">Statut</label>
            <select id="f-status">${statusOptions}</select>
          </div>
          <div class="field">
            <label for="f-verifier">Vérificateur</label>
            <select id="f-verifier">
              <option value="">Tous les vérificateurs</option>
              ${verifierOptions}
            </select>
          </div>
          <button class="btn" id="f-clear" type="button">Réinitialiser les filtres</button>
        </div>

        <div class="table-wrap">
          <table class="data">
            <thead>
              <tr>
                <th>Référence</th><th>Nom</th><th>Type</th><th>État</th><th>Statut</th>
                <th>Vérificateur</th><th>Date du dossier</th><th>Date de retrait</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              ${
                rows ||
                `<tr><td colspan="9" class="empty">Aucun dossier ne correspond aux filtres actuels.</td></tr>`
              }
              <tr id="f-empty" hidden>
                <td colspan="9" class="empty">Aucun dossier ne correspond à la recherche.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>`;

    /* Recherche libre : filtre instantané sur les lignes déjà affichées
       (référence, nom, type, état, statut, vérificateur, dates), sans requête. */
    const searchInput = document.getElementById("f-q");
    const emptyRow = document.getElementById("f-empty");
    const applySearch = () => {
      const term = fold(searchInput.value).trim();
      state.filters.q = searchInput.value;
      const rows = app.querySelectorAll("tbody tr.hoverable");
      let visible = 0;
      rows.forEach((tr) => {
        const match = !term || fold(tr.textContent).includes(term);
        tr.hidden = !match;
        if (match) visible += 1;
      });
      // Le message « aucun résultat de recherche » ne double pas celui des filtres.
      if (emptyRow) emptyRow.hidden = visible > 0 || rows.length === 0;
    };
    searchInput.addEventListener("input", applySearch);
    searchInput.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") {
        searchInput.value = "";
        applySearch();
      }
    });
    applySearch();
    if (searchInput.value) {
      searchInput.focus();
      searchInput.setSelectionRange(searchInput.value.length, searchInput.value.length);
    }

    const rerender = () => {
      state.filters.q = document.getElementById("f-q").value;
      state.filters.type = document.getElementById("f-type").value;
      state.filters.state = document.getElementById("f-state").value;
      state.filters.status = document.getElementById("f-status").value;
      state.filters.verifier_id = document.getElementById("f-verifier").value;
      renderList();
    };
    document.getElementById("f-type").addEventListener("change", rerender);
    document.getElementById("f-state").addEventListener("change", rerender);
    document.getElementById("f-status").addEventListener("change", rerender);
    document.getElementById("f-verifier").addEventListener("change", rerender);
    document.getElementById("f-clear").addEventListener("click", () => {
      state.filters = { q: "", type: "", state: "", status: "", verifier_id: "" };
      renderList();
    });
    app.querySelectorAll("tbody tr.hoverable").forEach((tr) => {
      tr.addEventListener("click", (ev) => {
        if (ev.target.closest("a, button")) return;
        location.hash = `#/dossiers/${tr.dataset.id}`;
      });
    });
    app.querySelectorAll("[data-del-dossier]").forEach((btn) => {
      btn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        const id = Number(btn.dataset.delDossier);
        if (!window.confirm("Supprimer ce dossier ?")) return;
        btn.disabled = true;
        try {
          await api(`/api/dossiers/${id}`, { method: "DELETE" });
          renderList();
        } catch (err) {
          btn.disabled = false;
          if (err.message === "Session expirée") return;
          window.alert(err.message);
        }
      });
    });
  } catch (err) {
    if (err.message !== "Session expirée") renderError(err);
  }
}

function buildFilterQuery() {
  const params = new URLSearchParams();
  if (state.filters.type) params.set("type", state.filters.type);
  if (state.filters.state) params.set("state", state.filters.state);
  if (state.filters.status) params.set("status", state.filters.status);
  if (state.filters.verifier_id) params.set("verifier_id", state.filters.verifier_id);
  const qs = params.toString();
  return qs ? "?" + qs : "";
}

/* ------------------------------------------------------------------ */
/* Détail d'un dossier                                                */
/* ------------------------------------------------------------------ */

function remarkList(remarks) {
  if (!remarks.length) {
    return `<p class="empty">Aucune remarque pour le moment.</p>`;
  }
  return `<ul class="remark-list">${remarks
    .map(
      (r) => `<li>
        <div class="remark-meta">
          <span class="who">${esc(r.author_name)}</span>
          <span>${esc(fmtDate(r.date))}</span>
        </div>
        <div class="remark-text">${esc(r.comment_text)}</div>
      </li>`
    )
    .join("")}</ul>`;
}

async function renderDetail(id) {
  setActiveNav("dossiers");
  closePopovers();
  const app = document.getElementById("app");
  app.innerHTML = `<p class="muted">Chargement…</p>`;
  try {
    const [d, remarks] = await Promise.all([
      api(`/api/dossiers/${id}`),
      api(`/api/dossiers/${id}/remarks`),
    ]);

    const parentHtml = d.parent_dossier_id
      ? `<a href="#/dossiers/${d.parent_dossier_id}">${esc(d.parent_reference)} — ${esc(
          d.parent_name
        )}</a>`
      : `<span class="muted">Aucun</span>`;

    app.innerHTML = `
      <div class="breadcrumb"><a href="#/dossiers">← Tous les dossiers</a></div>

      <section class="card">
        <div class="detail-head">
          <div>
            <div class="ref-big">${esc(d.reference_number)}</div>
            <h1>${esc(d.name)}</h1>
          </div>
          <div style="display:flex;gap:8px;align-items:center;">
            ${stateBadge(d.state)}
            ${statusBadge(d.status)}
            <a class="btn btn-sm" href="#/dossiers/${d.id}/edit">Modifier</a>
            <button class="btn btn-sm btn-danger" id="detail-delete" type="button">Supprimer</button>
          </div>
        </div>

        <div class="grid">
          <div>
            <span class="field-label">Type</span>
            <span class="field-value">${typeBadge(d.type)}</span>
          </div>
          <div>
            <span class="field-label">Vérificateur</span>
            <span class="field-value">${esc(d.verifier_name)}
              <span class="auto-note">rempli depuis votre compte · non modifiable</span>
            </span>
          </div>
          <div>
            <span class="field-label">État</span>
            <span class="field-value">
              ${stateBadge(d.state)}
              <button class="btn btn-sm" id="toggle-retire" type="button">${
                d.state === "Retiré" ? "Annuler le retrait" : "Retirer"
              }</button>
            </span>
          </div>
          <div>
            <span class="field-label">Statut</span>
            <span class="field-value">
              ${statusBadge(d.status)}
              <button class="btn btn-sm" id="toggle-status" type="button">Changer le statut</button>
            </span>
          </div>
          <div>
            <span class="field-label">Date de retrait</span>
            <span class="field-value">${esc(fmtDate(d.withdrawal_date))}</span>
          </div>
          <div>
            <span class="field-label">Retiré par</span>
            <span class="field-value">${
              d.withdrawn_by
                ? esc(d.withdrawn_by)
                : `<span class="muted">—</span>`
            }</span>
          </div>
          <div>
            <span class="field-label">Date du dossier</span>
            <span class="field-value">${esc(fmtDate(d.created_date))}</span>
          </div>
          <div>
            <span class="field-label">Dossier parent</span>
            <span class="field-value">${parentHtml}</span>
          </div>
          <div style="grid-column:1/-1;">
            <span class="field-label">Observation</span>
            <span class="field-value pre-line">${
              d.observation ? esc(d.observation) : `<span class="muted">Aucune observation</span>`
            }</span>
          </div>
        </div>

        <div id="retire-panel" class="action-panel" hidden>
          <form id="retire-form">
            <h3>Retirer le dossier</h3>
            <div class="error" id="retire-error" hidden></div>
            <div class="grid">
              <div class="field">
                <label for="w-name">Nom de la personne qui retire</label>
                <input id="w-name" name="withdrawn_by" maxlength="200" required
                       placeholder="Nom et prénom">
              </div>
              <div class="field">
                <label>Date de retrait</label>
                <input value="${esc(fmtDate(todayIso()))}" readonly>
                <p class="hint">Renseignée automatiquement le jour du retrait. Le statut passe à « Retour » s'il était « En cours ».</p>
              </div>
              <div class="field" style="grid-column:1/-1;">
                <label for="w-remark">Remarque</label>
                <textarea id="w-remark" name="remark" maxlength="5000"
                          placeholder="Facultatif — motif du retrait, précision…"></textarea>
              </div>
            </div>
            <div class="form-actions">
              <button class="btn btn-primary" type="submit">Confirmer le retrait</button>
              <button class="btn" id="retire-cancel" type="button">Annuler</button>
            </div>
          </form>
        </div>

        <div id="status-panel" class="action-panel" hidden>
          <form id="status-form">
            <h3>Changer le statut</h3>
            <div class="error" id="status-error" hidden></div>
            <div class="grid">
              <div class="field">
                <label for="s-status">Nouveau statut</label>
                <select id="s-status" name="status">
                  ${state.meta.statuses
                    .map(
                      (s) =>
                        `<option value="${esc(s)}" ${
                          d.status === s ? "selected" : ""
                        }>${esc(s)}</option>`
                    )
                    .join("")}
                </select>
              </div>
              <div class="field" style="grid-column:1/-1;">
                <label for="s-remark">Remarque</label>
                <textarea id="s-remark" name="remark" maxlength="5000"
                          placeholder="Facultatif — précisez le motif, surtout en cas de rejet"></textarea>
              </div>
            </div>
            <div class="form-actions">
              <button class="btn btn-primary" type="submit">Enregistrer le statut</button>
              <button class="btn" id="status-cancel" type="button">Annuler</button>
            </div>
          </form>
        </div>
      </section>

      <section class="card">
        <h2>Remarques</h2>
        <form id="remark-form">
          <div class="field">
            <label for="r-text">Ajouter une remarque</label>
            <textarea id="r-text" name="comment_text" placeholder="Observation, constat, note…" required></textarea>
          </div>
          <div class="form-actions" style="justify-content:flex-start;">
            <button class="btn btn-primary" type="submit">Ajouter la remarque</button>
          </div>
          <div class="error" id="remark-error" hidden></div>
        </form>
        <div id="remarks-container">${remarkList(remarks)}</div>
      </section>`;

    document.getElementById("detail-delete").addEventListener("click", async () => {
      if (!window.confirm(`Supprimer le dossier ${d.reference_number} ?`)) return;
      try {
        await api(`/api/dossiers/${d.id}`, { method: "DELETE" });
        location.hash = "#/dossiers";
      } catch (err) {
        if (err.message === "Session expirée") return;
        window.alert(err.message);
      }
    });

    document
      .getElementById("remark-form")
      .addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const form = ev.target;
        const errorBox = document.getElementById("remark-error");
        const button = form.querySelector("button[type=submit]");
        errorBox.hidden = true;
        button.disabled = true;
        try {
          await api(`/api/dossiers/${id}/remarks`, {
            method: "POST",
            body: { comment_text: form.elements.comment_text.value },
          });
          renderDetail(id);
        } catch (err) {
          if (err.message === "Session expirée") return;
          errorBox.textContent = err.message;
          errorBox.hidden = false;
          button.disabled = false;
        }
      });

    /* --- Retirer / annuler le retrait -------------------------------- */
    const retirePanel = document.getElementById("retire-panel");
    const statusPanel = document.getElementById("status-panel");

    document.getElementById("toggle-retire").addEventListener("click", async () => {
      if (d.state === "Retiré") {
        if (!window.confirm(`Remettre le dossier ${d.reference_number} à l'état « Reçu » ?`)) return;
        try {
          await api(`/api/dossiers/${d.id}/receive`, { method: "POST", body: {} });
          renderDetail(id);
        } catch (err) {
          if (err.message === "Session expirée") return;
          window.alert(err.message);
        }
        return;
      }
      openPopover(retirePanel, document.getElementById("toggle-retire"));
    });

    document.getElementById("retire-cancel").addEventListener("click", closePopovers);

    document.getElementById("retire-form").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const form = ev.target;
      const errorBox = document.getElementById("retire-error");
      const button = form.querySelector("button[type=submit]");
      errorBox.hidden = true;
      button.disabled = true;
      try {
        await api(`/api/dossiers/${d.id}/withdraw`, {
          method: "POST",
          body: {
            withdrawn_by: form.elements.withdrawn_by.value,
            remark: form.elements.remark.value,
          },
        });
        renderDetail(id);
      } catch (err) {
        if (err.message === "Session expirée") return;
        errorBox.textContent = err.message;
        errorBox.hidden = false;
        button.disabled = false;
      }
    });

    /* --- Changement de statut ---------------------------------------- */
    document.getElementById("toggle-status").addEventListener("click", () => {
      openPopover(statusPanel, document.getElementById("toggle-status"));
    });

    document.getElementById("status-cancel").addEventListener("click", closePopovers);

    document.getElementById("status-form").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const form = ev.target;
      const errorBox = document.getElementById("status-error");
      const button = form.querySelector("button[type=submit]");
      errorBox.hidden = true;
      button.disabled = true;
      try {
        await api(`/api/dossiers/${d.id}/status`, {
          method: "POST",
          body: {
            status: form.elements.status.value,
            remark: form.elements.remark.value,
          },
        });
        renderDetail(id);
      } catch (err) {
        if (err.message === "Session expirée") return;
        errorBox.textContent = err.message;
        errorBox.hidden = false;
        button.disabled = false;
      }
    });
  } catch (err) {
    if (err.message === "Session expirée") return;
    renderError(err);
  }
}

/* ------------------------------------------------------------------ */
/* Formulaire de création / modification                              */
/* ------------------------------------------------------------------ */

async function renderForm(id) {
  setActiveNav(id ? "dossiers" : "new");
  const app = document.getElementById("app");
  app.innerHTML = `<p class="muted">Chargement…</p>`;
  try {
    const isEdit = id != null;
    const [dossier, allDossiers] = await Promise.all([
      isEdit ? api(`/api/dossiers/${id}`) : Promise.resolve(null),
      api("/api/dossiers"),
    ]);

    const currentType = dossier ? dossier.type : "";
    const parentChoices = allDossiers.filter((d) => !isEdit || d.id !== dossier.id);

    const typeOptions = state.meta.types
      .map(
        (t) =>
          `<option value="${esc(t.value)}" ${
            currentType === t.value ? "selected" : ""
          }>${esc(t.label)} (${esc(typeRangeLabel(t))})</option>`
      )
      .join("");

    const stateOptions = state.meta.states
      .map((s) => {
        const selected = dossier ? dossier.state === s : s === state.meta.default_state;
        return `<option value="${esc(s)}" ${selected ? "selected" : ""}>${esc(s)}</option>`;
      })
      .join("");

    const statusOptions = state.meta.statuses
      .map((s) => {
        const selected = dossier ? dossier.status === s : s === state.meta.default_status;
        return `<option value="${esc(s)}" ${selected ? "selected" : ""}>${esc(s)}</option>`;
      })
      .join("");

    const parentOptions = [
      `<option value="">— Aucun —</option>`,
      ...parentChoices
        .sort((a, b) => a.reference_number.localeCompare(b.reference_number))
        .map(
          (d) =>
            `<option value="${d.id}" ${
              dossier && dossier.parent_dossier_id === d.id ? "selected" : ""
            }>${esc(d.reference_number)} — ${esc(d.name)}</option>`
        ),
    ].join("");

    const dateValue = dossier ? dossier.created_date : todayIso();

    app.innerHTML = `
      <div class="breadcrumb"><a href="${
        isEdit ? `#/dossiers/${id}` : "#/dossiers"
      }">← Retour</a></div>
      <div class="page-head"><h1>${isEdit ? "Modifier le dossier" : "Nouveau dossier"}</h1></div>

      <section class="card">
        <form id="dossier-form">
          <div class="error" id="form-error" hidden></div>

          <div class="grid">
            <div class="field">
              <label for="d-name">Nom</label>
              <input id="d-name" name="name" maxlength="300" required
                     value="${esc(dossier ? dossier.name : "")}"
                     placeholder="Description courte du dossier">
            </div>

            <div class="field">
              <label for="d-type">Type</label>
              <select id="d-type" name="type" ${isEdit ? "disabled" : ""} required>
                <option value="">— Choisir un type —</option>
                ${typeOptions}
              </select>
              ${
                isEdit
                  ? `<p class="hint">Le type est définitif après création : il détermine la plage de numéros.</p>`
                  : `<p class="hint">Chaque type utilise sa propre série de numéros.</p>`
              }
            </div>

            <div class="field">
              <label for="d-state">État</label>
              <select id="d-state" name="state">${stateOptions}</select>
              <p class="hint">Un nouveau dossier est « Reçu » ; passez à « Retiré » si le dossier est retiré.</p>
            </div>

            <div class="field">
              <label for="d-status">Statut</label>
              <select id="d-status" name="status">${statusOptions}</select>
              <p class="hint">${
                isEdit
                  ? "Vous pouvez aussi changer le statut depuis la fiche du dossier."
                  : "Proposé à « En cours » ; modifiable dès la création."
              }</p>
            </div>

            <div class="field">
              <label for="d-date">Date du dossier</label>
              <input id="d-date" name="created_date" type="date" required value="${esc(dateValue)}">
              <p class="hint">Remplie automatiquement, modifiable si besoin.</p>
            </div>

            <div class="field">
              <label for="d-parent">Dossier parent</label>
              <select id="d-parent" name="parent_dossier_id">${parentOptions}</select>
              <p class="hint">Facultatif — pour le suivi des dépendances.</p>
            </div>

            <div class="field">
              <label for="d-verifier">Vérificateur</label>
              <input id="d-verifier" value="${esc(state.user.display_name)}" readonly>
              <p class="hint">Renseigné automatiquement depuis votre compte · non modifiable.</p>
            </div>

            <div class="field" style="grid-column:1/-1;">
              <label for="d-observation">Observation</label>
              <textarea id="d-observation" name="observation" maxlength="5000"
                        placeholder="Facultatif — note libre sur le dossier">${esc(
                          dossier && dossier.observation ? dossier.observation : ""
                        )}</textarea>
            </div>
          </div>

          <div class="form-actions">
            <button class="btn btn-primary" type="submit">${isEdit ? "Enregistrer les modifications" : "Créer le dossier"}</button>
            <a class="btn" href="${isEdit ? `#/dossiers/${id}` : "#/dossiers"}">Annuler</a>
          </div>
        </form>
      </section>`;

    document
      .getElementById("dossier-form")
      .addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const form = ev.target;
        const errorBox = document.getElementById("form-error");
        const button = form.querySelector("button[type=submit]");
        errorBox.hidden = true;
        button.disabled = true;

        const parentId = form.elements.parent_dossier_id.value;
        const payload = {
          name: form.elements.name.value,
          state: form.elements.state.value,
          status: form.elements.status.value,
          created_date: form.elements.created_date.value,
          parent_dossier_id: parentId ? Number(parentId) : null,
          observation: form.elements.observation.value,
        };
        if (!isEdit) payload.type = form.elements.type.value;

        try {
          const saved = isEdit
            ? await api(`/api/dossiers/${id}`, { method: "PUT", body: payload })
            : await api("/api/dossiers", { method: "POST", body: payload });
          location.hash = `#/dossiers/${saved.id}`;
        } catch (err) {
          if (err.message === "Session expirée") return;
          errorBox.textContent = err.message;
          errorBox.hidden = false;
          button.disabled = false;
        }
      });
  } catch (err) {
    if (err.message === "Session expirée") return;
    renderError(err);
  }
}

/* ------------------------------------------------------------------ */
/* Gestion des utilisateurs                                           */
/* ------------------------------------------------------------------ */

function roleOptions(current) {
  const roles = (state.meta && state.meta.roles) || ["admin"];
  return roles
    .map(
      (r) => `<option value="${esc(r)}" ${current === r ? "selected" : ""}>${esc(r)}</option>`
    )
    .join("");
}

function userFormHtml(editing) {
  if (editing) {
    return `
      <form id="user-form">
        <div class="error" id="user-error" hidden></div>
        <div class="grid">
          <div class="field">
            <label for="u-name">Nom affiché</label>
            <input id="u-name" name="display_name" maxlength="100" required
                   value="${esc(editing.display_name)}">
          </div>
          <div class="field">
            <label for="u-username">Identifiant</label>
            <input id="u-username" value="${esc(editing.username)}" readonly>
            <p class="hint">L'identifiant de connexion ne peut pas être modifié après création.</p>
          </div>
          <div class="field">
            <label for="u-role">Rôle</label>
            <select id="u-role" name="role">${roleOptions(editing.role)}</select>
          </div>
          <div class="field">
            <label for="u-password">Nouveau mot de passe (facultatif)</label>
            <input id="u-password" name="password" type="password"
                   autocomplete="new-password" placeholder="Laisser vide pour ne pas changer">
          </div>
          <div class="field">
            <label class="check-line" for="u-actif">
              <input id="u-actif" name="actif" type="checkbox" ${editing.actif ? "checked" : ""}>
              Compte actif (autorise la connexion)
            </label>
          </div>
        </div>
        <div class="form-actions">
          <button class="btn btn-primary" type="submit">Enregistrer</button>
          <button class="btn" type="button" id="user-cancel">Annuler</button>
        </div>
      </form>`;
  }
  return `
      <form id="user-form">
        <div class="error" id="user-error" hidden></div>
        <div class="grid">
          <div class="field">
            <label for="u-username">Identifiant</label>
            <input id="u-username" name="username" maxlength="50" required
                   placeholder="ex. jdupont">
            <p class="hint">Sert d'identifiant de connexion, avec le mot de passe.</p>
          </div>
          <div class="field">
            <label for="u-name">Nom affiché</label>
            <input id="u-name" name="display_name" maxlength="100" required
                   placeholder="ex. Jean Dupont">
          </div>
          <div class="field">
            <label for="u-password">Mot de passe</label>
            <input id="u-password" name="password" type="password" minlength="4"
                   autocomplete="new-password" required>
          </div>
          <div class="field">
            <label for="u-role">Rôle</label>
            <select id="u-role" name="role">${roleOptions("admin")}</select>
          </div>
          <div class="field">
            <label class="check-line" for="u-actif">
              <input id="u-actif" name="actif" type="checkbox" checked>
              Compte actif (autorise la connexion)
            </label>
          </div>
        </div>
        <div class="form-actions">
          <button class="btn btn-primary" type="submit">Créer l'utilisateur</button>
        </div>
      </form>`;
}

async function renderUsers() {
  setActiveNav("users");
  const app = document.getElementById("app");
  app.innerHTML = `<div class="page-head"><h1>Utilisateurs</h1></div><p class="muted">Chargement…</p>`;
  try {
    const users = await api("/api/users");
    const editing = state.usersEditId
      ? users.find((u) => u.id === state.usersEditId) || null
      : null;
    if (state.usersEditId && !editing) state.usersEditId = null;

    const rows = users
      .map(
        (u) => `<tr>
            <td><strong>${esc(u.display_name)}</strong>${
              u.id === state.user.id ? ` <span class="muted small">(vous)</span>` : ""
            }</td>
            <td class="ref">${esc(u.username)}</td>
            <td><span class="badge badge-type">${esc(u.role)}</span></td>
            <td>${
              u.actif
                ? `<span class="badge badge-vise">Actif</span>`
                : `<span class="badge badge-retire">Désactivé</span>`
            }</td>
            <td>${esc(fmtDate(u.created_at))}</td>
            <td class="num">${u.dossier_count || 0}</td>
            <td>
              <div class="row-actions">
                <button class="btn btn-sm" data-edit="${u.id}" type="button">Modifier</button>
                <button class="btn btn-sm btn-danger" data-delete="${u.id}" type="button">Supprimer</button>
              </div>
            </td>
          </tr>`
      )
      .join("");

    app.innerHTML = `
      <div class="page-head"><h1>Utilisateurs</h1></div>

      <section class="card">
        <h2>${editing ? `Modifier l'utilisateur « ${esc(editing.username)} »` : "Nouvel utilisateur"}</h2>
        ${userFormHtml(editing)}
      </section>

      <section class="card">
        <h2>Comptes</h2>
        <div class="table-wrap">
          <table class="data">
            <thead>
              <tr>
                <th>Nom affiché</th><th>Identifiant</th><th>Rôle</th><th>Statut</th>
                <th>Créé le</th><th class="num">Dossiers</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              ${rows || `<tr><td colspan="7" class="empty">Aucun utilisateur.</td></tr>`}
            </tbody>
          </table>
        </div>
      </section>`;

    const form = document.getElementById("user-form");
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const errorBox = document.getElementById("user-error");
      const button = form.querySelector("button[type=submit]");
      errorBox.hidden = true;
      button.disabled = true;
      try {
        if (editing) {
          const body = {
            display_name: form.elements.display_name.value,
            role: form.elements.role.value,
            actif: form.elements.actif.checked,
          };
          if (form.elements.password.value) body.password = form.elements.password.value;
          await api(`/api/users/${editing.id}`, { method: "PUT", body });
          state.usersEditId = null;
        } else {
          await api("/api/users", {
            method: "POST",
            body: {
              username: form.elements.username.value,
              display_name: form.elements.display_name.value,
              password: form.elements.password.value,
              role: form.elements.role.value,
              actif: form.elements.actif.checked,
            },
          });
        }
        renderUsers();
      } catch (err) {
        if (err.message === "Session expirée") return;
        errorBox.textContent = err.message;
        errorBox.hidden = false;
        button.disabled = false;
      }
    });

    const cancel = document.getElementById("user-cancel");
    if (cancel) {
      cancel.addEventListener("click", () => {
        state.usersEditId = null;
        renderUsers();
      });
    }

    app.querySelectorAll("[data-edit]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.usersEditId = Number(btn.dataset.edit);
        renderUsers();
      });
    });

    app.querySelectorAll("[data-delete]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = Number(btn.dataset.delete);
        const target = users.find((u) => u.id === id);
        if (!target) return;
        if (!window.confirm(`Supprimer l'utilisateur « ${target.username} » ?`)) return;
        try {
          await api(`/api/users/${id}`, { method: "DELETE" });
          if (state.usersEditId === id) state.usersEditId = null;
          renderUsers();
        } catch (err) {
          if (err.message === "Session expirée") return;
          window.alert(err.message);
        }
      });
    });
  } catch (err) {
    if (err.message === "Session expirée") return;
    renderError(err);
  }
}

/* ------------------------------------------------------------------ */
/* Données : export, import et réinitialisation de la base            */
/* ------------------------------------------------------------------ */

function fmtSize(bytes) {
  const n = Number(bytes) || 0;
  if (n < 1024) return `${n} o`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} Ko`;
  return `${(n / (1024 * 1024)).toFixed(1)} Mo`;
}

/* Téléchargement de la base : l'API exige le jeton Bearer, un simple lien ne
   suffit donc pas. Le fichier est récupéré puis enregistré par le navigateur. */
async function downloadDatabase(button) {
  const errorBox = document.getElementById("export-error");
  errorBox.hidden = true;
  button.disabled = true;
  try {
    const res = await fetch(apiUrl("/api/database/export"), {
      headers: { Authorization: "Bearer " + state.token },
    });
    if (res.status === 401) {
      clearSession();
      route("Votre session a expiré. Veuillez vous reconnecter.");
      return;
    }
    if (!res.ok) {
      let data = null;
      try {
        data = await res.json();
      } catch (err) {
        /* corps vide */
      }
      throw new Error(detailMessage(data, res));
    }
    const blob = await res.blob();
    const entete = res.headers.get("Content-Disposition") || "";
    const trouve = /filename="?([^";]+)"?/.exec(entete);
    const nom = trouve ? trouve[1] : "dossiers.db";
    const url = URL.createObjectURL(blob);
    const lien = document.createElement("a");
    lien.href = url;
    lien.download = nom;
    document.body.appendChild(lien);
    lien.click();
    lien.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (err) {
    if (err.message === "Session expirée") return;
    errorBox.textContent = err.message;
    errorBox.hidden = false;
  } finally {
    button.disabled = false;
  }
}

/* Envoi d'un fichier .db en corps brut (pas de multipart côté serveur). */
async function uploadDatabase(fichier) {
  const corps = await fichier.arrayBuffer();
  const res = await fetch(apiUrl("/api/database/import"), {
    method: "POST",
    headers: {
      Authorization: "Bearer " + state.token,
      "Content-Type": "application/octet-stream",
    },
    body: corps,
  });
  let data = null;
  try {
    data = await res.json();
  } catch (err) {
    /* corps vide */
  }
  if (res.status === 401) throw new Error("Session expirée");
  if (!res.ok) throw new Error(detailMessage(data, res));
  return data;
}

async function renderData() {
  setActiveNav("data");
  closePopovers();
  const app = document.getElementById("app");
  app.innerHTML = `<div class="page-head"><h1>Données</h1></div><p class="muted">Chargement…</p>`;
  try {
    const info = await api("/api/database/info");

    app.innerHTML = `
      <div class="page-head"><h1>Données</h1></div>

      <section class="card">
        <h2>Base actuelle</h2>
        <div class="grid">
          <div>
            <span class="field-label">Fichier</span>
            <span class="field-value small" style="word-break:break-all;">${esc(info.path)}</span>
          </div>
          <div>
            <span class="field-label">Taille</span>
            <span class="field-value">${esc(fmtSize(info.size_bytes))}</span>
          </div>
          <div>
            <span class="field-label">Dossiers</span>
            <span class="field-value">${info.dossiers}</span>
          </div>
          <div>
            <span class="field-label">Utilisateurs</span>
            <span class="field-value">${info.users}</span>
          </div>
          <div>
            <span class="field-label">Remarques</span>
            <span class="field-value">${info.remarks}</span>
          </div>
          <div>
            <span class="field-label">Points de contrôle</span>
            <span class="field-value">${info.checkpoints}</span>
          </div>
        </div>
      </section>

      <section class="card">
        <h2>Exporter</h2>
        <p class="muted">Télécharge une copie complète de la base (dossiers, remarques, utilisateurs, compteurs) dans un fichier <code>.db</code>. Conservez ce fichier : c'est votre sauvegarde.</p>
        <div class="form-actions" style="justify-content:flex-start;">
          <button class="btn btn-primary" id="export-btn" type="button">Télécharger la base (.db)</button>
        </div>
        <div class="error" id="export-error" hidden></div>
      </section>

      <section class="card">
        <h2>Importer</h2>
        <p class="muted">Restaure un fichier <code>.db</code> exporté depuis cette application. Toutes les données actuelles sont remplacées : exportez d'abord la base actuelle si vous voulez pouvoir revenir en arrière.</p>
        <div class="field">
          <label for="import-file">Fichier de sauvegarde (.db)</label>
          <input id="import-file" type="file" accept=".db,.sqlite,.sqlite3">
        </div>
        <div class="error" id="import-error" hidden></div>
        <div class="form-actions" style="justify-content:flex-start;">
          <button class="btn btn-primary" id="import-btn" type="button">Importer et remplacer</button>
        </div>
        <p class="hint">Après l'import, la session est fermée : reconnectez-vous avec un compte présent dans la base importée.</p>
      </section>

      <section class="card">
        <h2>Réinitialiser</h2>
        <p class="muted">Efface définitivement tous les dossiers, remarques, comptes et compteurs, puis recrée une base neuve avec le compte <code>admin</code> / <code>admin</code> et les points de contrôle.</p>
        <div class="field">
          <label for="reset-confirm">Tapez <code>REINITIALISER</code> pour confirmer</label>
          <input id="reset-confirm" autocomplete="off" placeholder="REINITIALISER">
        </div>
        <div class="error" id="reset-error" hidden></div>
        <div class="form-actions" style="justify-content:flex-start;">
          <button class="btn btn-danger" id="reset-btn" type="button" disabled>Réinitialiser la base</button>
        </div>
      </section>`;

    /* --- Export ------------------------------------------------------ */
    const exportBtn = document.getElementById("export-btn");
    exportBtn.addEventListener("click", () => downloadDatabase(exportBtn));

    /* --- Import ------------------------------------------------------ */
    const importInput = document.getElementById("import-file");
    const importBtn = document.getElementById("import-btn");
    const importError = document.getElementById("import-error");
    importBtn.addEventListener("click", async () => {
      importError.hidden = true;
      const fichier = importInput.files && importInput.files[0];
      if (!fichier) {
        importError.textContent = "Choisissez d'abord un fichier .db à importer.";
        importError.hidden = false;
        return;
      }
      if (
        !window.confirm(
          `Remplacer toutes les données actuelles par celles de « ${fichier.name} » ?`
        )
      )
        return;
      importBtn.disabled = true;
      try {
        const data = await uploadDatabase(fichier);
        clearSession();
        renderLogin(
          `Base importée : ${data.dossiers} dossier(s), ${data.users} utilisateur(s). ` +
            "Reconnectez-vous avec un compte présent dans cette base.",
          "notice"
        );
      } catch (err) {
        if (err.message === "Session expirée") {
          clearSession();
          route("Votre session a expiré. Veuillez vous reconnecter.");
          return;
        }
        importError.textContent = err.message;
        importError.hidden = false;
        importBtn.disabled = false;
      }
    });

    /* --- Réinitialisation -------------------------------------------- */
    const resetInput = document.getElementById("reset-confirm");
    const resetBtn = document.getElementById("reset-btn");
    const resetError = document.getElementById("reset-error");
    resetInput.addEventListener("input", () => {
      resetBtn.disabled = resetInput.value.trim().toUpperCase() !== "REINITIALISER";
    });
    resetBtn.addEventListener("click", async () => {
      if (
        !window.confirm(
          "Réinitialiser la base ? Tous les dossiers, remarques et comptes " +
            "seront définitivement supprimés."
        )
      )
        return;
      resetError.hidden = true;
      resetBtn.disabled = true;
      try {
        await api("/api/database/reset", { method: "POST", body: {} });
        clearSession();
        renderLogin(
          "Base réinitialisée. Connectez-vous avec le compte par défaut admin / admin.",
          "notice"
        );
      } catch (err) {
        if (err.message === "Session expirée") return;
        resetError.textContent = err.message;
        resetError.hidden = false;
        resetBtn.disabled = false;
      }
    });
  } catch (err) {
    if (err.message === "Session expirée") return;
    renderError(err);
  }
}

/* ------------------------------------------------------------------ */
/* Routeur                                                            */
/* ------------------------------------------------------------------ */

function route(message) {
  if (!state.token || !state.user) {
    renderLogin(message);
    return;
  }
  showAppChrome();

  const hash = (location.hash || "#/").replace(/^#\/?/, "");
  const parts = hash.split("/").filter(Boolean);

  if (parts[0] === "users") {
    renderUsers();
    return;
  }
  if (parts[0] === "data") {
    renderData();
    return;
  }
  if (parts[0] !== "dossiers" || parts.length === 0) {
    renderDashboard();
    return;
  }
  if (parts.length === 1) {
    renderList();
    return;
  }
  if (parts[1] === "new") {
    renderForm(null);
    return;
  }
  const id = Number(parts[1]);
  if (!Number.isFinite(id)) {
    renderDashboard();
    return;
  }
  if (parts[2] === "edit") {
    renderForm(id);
    return;
  }
  renderDetail(id);
}

/* ------------------------------------------------------------------ */
/* Démarrage                                                          */
/* ------------------------------------------------------------------ */

document.getElementById("logout-btn").addEventListener("click", signOut);
window.addEventListener("hashchange", () => {
  state.usersEditId = null;
  route();
});

(async function boot() {
  if (state.token) {
    try {
      state.user = await api("/api/me");
      state.meta = await api("/api/meta");
    } catch (err) {
      /* 401 géré dans api() : session effacée */
    }
  }
  route();
})();
