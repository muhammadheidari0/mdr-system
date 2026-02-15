import {
  addMonths,
  endOfMonth,
  format,
  getDay,
  isValid,
  parse,
  setDate,
  startOfMonth,
  subMonths,
} from "date-fns-jalali";

const STYLE_ID = "shamsi-date-input-style";
const WEEKDAY_LABELS = ["ش", "ی", "د", "س", "چ", "پ", "ج"];

interface ShamsiFieldController {
  syncFromSource: () => void;
}

export interface ShamsiDateRegistry {
  syncAll: () => void;
}

function ensureStyle(): void {
  if (document.getElementById(STYLE_ID)) return;
  const styleEl = document.createElement("style");
  styleEl.id = STYLE_ID;
  styleEl.textContent = `
.shamsi-date-wrap{position:relative;display:flex;align-items:center;width:100%}
.shamsi-date-display{direction:ltr;text-align:left;padding-inline-start:2.25rem}
.shamsi-date-btn{position:absolute;inset-inline-start:.5rem;top:50%;transform:translateY(-50%);border:0;background:transparent;color:#64748b;cursor:pointer;display:flex;align-items:center;justify-content:center;padding:0}
.shamsi-date-btn .material-icons-round{font-size:1.1rem;line-height:1}
.shamsi-date-popup{position:fixed;z-index:5000;background:#fff;border:1px solid #dbe3ef;border-radius:10px;box-shadow:0 16px 42px rgba(15,23,42,.16);padding:.6rem;min-width:248px}
.shamsi-date-popup[hidden]{display:none}
.shamsi-date-head{display:flex;align-items:center;justify-content:space-between;gap:.4rem;margin-bottom:.45rem}
.shamsi-date-head-title{font-weight:700;color:#0f172a;font-size:.9rem}
.shamsi-date-nav{border:1px solid #d7e1ef;background:#f8fbff;color:#1e3a8a;border-radius:7px;padding:.2rem .45rem;cursor:pointer}
.shamsi-date-grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:.22rem}
.shamsi-date-week{font-size:.72rem;color:#64748b;text-align:center;padding:.18rem 0}
.shamsi-date-day{border:0;background:transparent;border-radius:8px;padding:.32rem 0;cursor:pointer;color:#0f172a}
.shamsi-date-day:hover{background:#eff6ff}
.shamsi-date-day.is-selected{background:#2563eb;color:#fff}
.shamsi-date-day.is-today{outline:1px solid #93c5fd}
.shamsi-date-foot{display:flex;justify-content:space-between;margin-top:.5rem}
.shamsi-date-foot-btn{border:1px solid #d7e1ef;background:#fff;color:#1e3a8a;border-radius:7px;padding:.18rem .5rem;cursor:pointer;font-size:.78rem}
`;
  document.head.appendChild(styleEl);
}

function normalizeDigits(raw: string): string {
  const map: Record<string, string> = {
    "۰": "0",
    "۱": "1",
    "۲": "2",
    "۳": "3",
    "۴": "4",
    "۵": "5",
    "۶": "6",
    "۷": "7",
    "۸": "8",
    "۹": "9",
    "٠": "0",
    "١": "1",
    "٢": "2",
    "٣": "3",
    "٤": "4",
    "٥": "5",
    "٦": "6",
    "٧": "7",
    "٨": "8",
    "٩": "9",
  };
  return String(raw || "")
    .replace(/[۰-۹٠-٩]/g, (char) => map[char] ?? char)
    .replace(/[.\-]/g, "/")
    .trim();
}

function parseGregorianInput(value: string): Date | null {
  const raw = String(value || "").trim();
  if (!raw) return null;
  const parsed = new Date(`${raw}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function toGregorianInput(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function parseJalaliInput(value: string): Date | null {
  const normalized = normalizeDigits(value);
  if (!normalized) return null;
  const match = normalized.match(/^(\d{4})\/(\d{1,2})\/(\d{1,2})$/);
  if (!match) return null;

  const y = Number(match[1]);
  const m = Number(match[2]);
  const d = Number(match[3]);
  if (!Number.isFinite(y) || !Number.isFinite(m) || !Number.isFinite(d)) return null;

  const parsed = parse(`${y}-${m}-${d}`, "yyyy-M-d", new Date());
  if (!isValid(parsed)) return null;
  const normalizedParsed = format(parsed, "yyyy-M-d");
  return normalizedParsed === `${y}-${m}-${d}` ? parsed : null;
}

function dispatchSourceChange(source: HTMLInputElement): void {
  source.dispatchEvent(new Event("input", { bubbles: true }));
  source.dispatchEvent(new Event("change", { bubbles: true }));
}

function attachShamsiField(source: HTMLInputElement): ShamsiFieldController | null {
  if (source.dataset.shamsiBound === "1") return null;
  ensureStyle();
  source.dataset.shamsiBound = "1";

  const parent = source.parentElement;
  if (!parent) return null;

  const wrapper = document.createElement("div");
  wrapper.className = "shamsi-date-wrap";

  source.type = "hidden";
  source.autocomplete = "off";
  source.tabIndex = -1;

  const display = document.createElement("input");
  display.type = "text";
  display.className = `${source.className || ""} shamsi-date-display`.trim();
  display.placeholder = "yyyy/mm/dd";
  display.autocomplete = "off";
  display.inputMode = "numeric";

  const button = document.createElement("button");
  button.type = "button";
  button.className = "shamsi-date-btn";
  button.innerHTML = `<span class="material-icons-round">calendar_month</span>`;

  parent.insertBefore(wrapper, source);
  wrapper.appendChild(source);
  wrapper.appendChild(display);
  wrapper.appendChild(button);

  const popup = document.createElement("div");
  popup.className = "shamsi-date-popup";
  popup.hidden = true;
  document.body.appendChild(popup);

  let open = false;
  let monthCursor = parseGregorianInput(source.value) || new Date();
  let detachDocumentHandler: (() => void) | null = null;

  function syncFromSource(): void {
    const parsed = parseGregorianInput(source.value);
    display.value = parsed ? format(parsed, "yyyy/MM/dd") : "";
    monthCursor = parsed || monthCursor || new Date();
    display.disabled = source.disabled;
    button.disabled = source.disabled;
  }

  function closePopup(): void {
    open = false;
    popup.hidden = true;
    if (detachDocumentHandler) {
      detachDocumentHandler();
      detachDocumentHandler = null;
    }
  }

  function positionPopup(): void {
    const rect = wrapper.getBoundingClientRect();
    const popupHeight = popup.offsetHeight || 320;
    let top = rect.bottom + 6;
    if (top + popupHeight > window.innerHeight - 8) {
      top = Math.max(8, rect.top - popupHeight - 6);
    }
    popup.style.top = `${top}px`;
    popup.style.left = `${Math.max(8, rect.left)}px`;
  }

  function setSourceFromDate(date: Date, emit = true): void {
    source.value = toGregorianInput(date);
    syncFromSource();
    if (emit) dispatchSourceChange(source);
  }

  function clearSource(emit = true): void {
    source.value = "";
    syncFromSource();
    if (emit) dispatchSourceChange(source);
  }

  function renderPopup(): void {
    const selected = parseGregorianInput(source.value);
    const todayMarker = format(new Date(), "yyyy/MM/dd");

    const monthStart = startOfMonth(monthCursor);
    const monthEnd = endOfMonth(monthCursor);
    const daysCount = Number(format(monthEnd, "d"));
    const monthTitle = format(monthCursor, "MMMM yyyy");
    const startOffset = (getDay(monthStart) + 1) % 7;
    const selectedKey = selected ? format(selected, "yyyy/MM/dd") : "";

    const weekdayRows = WEEKDAY_LABELS.map((label) => `<div class="shamsi-date-week">${label}</div>`).join("");
    const gapRows = Array.from({ length: startOffset })
      .map(() => `<div aria-hidden="true"></div>`)
      .join("");
    const dayRows = Array.from({ length: daysCount })
      .map((_, idx) => {
        const day = idx + 1;
        const date = setDate(monthStart, day);
        const key = format(date, "yyyy/MM/dd");
        const selectedClass = key === selectedKey ? " is-selected" : "";
        const todayClass = key === todayMarker ? " is-today" : "";
        return `<button type="button" class="shamsi-date-day${selectedClass}${todayClass}" data-day="${day}">${day}</button>`;
      })
      .join("");

    popup.innerHTML = `
      <div class="shamsi-date-head">
        <button type="button" class="shamsi-date-nav" data-nav="next">›</button>
        <div class="shamsi-date-head-title">${monthTitle}</div>
        <button type="button" class="shamsi-date-nav" data-nav="prev">‹</button>
      </div>
      <div class="shamsi-date-grid">${weekdayRows}${gapRows}${dayRows}</div>
      <div class="shamsi-date-foot">
        <button type="button" class="shamsi-date-foot-btn" data-action="today">امروز</button>
        <button type="button" class="shamsi-date-foot-btn" data-action="clear">پاک</button>
      </div>
    `;
  }

  function openPopup(): void {
    if (source.disabled) return;
    monthCursor = parseGregorianInput(source.value) || new Date();
    renderPopup();
    positionPopup();
    popup.hidden = false;
    open = true;

    const onDocDown = (event: MouseEvent): void => {
      const target = event.target as Node | null;
      if (!target) return;
      if (popup.contains(target)) return;
      if (wrapper.contains(target)) return;
      closePopup();
    };
    const onResizeOrScroll = (): void => {
      if (!open) return;
      positionPopup();
    };

    document.addEventListener("mousedown", onDocDown, true);
    window.addEventListener("resize", onResizeOrScroll);
    window.addEventListener("scroll", onResizeOrScroll, true);
    detachDocumentHandler = () => {
      document.removeEventListener("mousedown", onDocDown, true);
      window.removeEventListener("resize", onResizeOrScroll);
      window.removeEventListener("scroll", onResizeOrScroll, true);
    };
  }

  function commitTypedValue(): void {
    const raw = String(display.value || "").trim();
    if (!raw) {
      clearSource(true);
      return;
    }
    const parsed = parseJalaliInput(raw);
    if (!parsed) {
      syncFromSource();
      return;
    }
    setSourceFromDate(parsed, true);
  }

  display.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      commitTypedValue();
      closePopup();
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      openPopup();
    }
  });
  display.addEventListener("blur", () => {
    commitTypedValue();
  });
  button.addEventListener("click", () => {
    if (open) {
      closePopup();
      return;
    }
    openPopup();
  });

  popup.addEventListener("click", (event) => {
    const target = event.target as HTMLElement | null;
    if (!target) return;

    const nav = target.closest<HTMLElement>("[data-nav]");
    if (nav) {
      const dir = String(nav.dataset.nav || "");
      monthCursor = dir === "prev" ? subMonths(monthCursor, 1) : addMonths(monthCursor, 1);
      renderPopup();
      return;
    }

    const action = target.closest<HTMLElement>("[data-action]");
    if (action) {
      const type = String(action.dataset.action || "");
      if (type === "today") {
        setSourceFromDate(new Date(), true);
        closePopup();
        return;
      }
      if (type === "clear") {
        clearSource(true);
        closePopup();
      }
      return;
    }

    const dayEl = target.closest<HTMLElement>("[data-day]");
    if (!dayEl) return;
    const day = Number(dayEl.dataset.day || 0);
    if (!Number.isFinite(day) || day <= 0) return;
    const date = setDate(startOfMonth(monthCursor), day);
    setSourceFromDate(date, true);
    closePopup();
  });

  syncFromSource();
  return { syncFromSource };
}

export function initShamsiDateInputs(inputIds: string[]): ShamsiDateRegistry {
  const controllers: ShamsiFieldController[] = [];
  (Array.isArray(inputIds) ? inputIds : []).forEach((id) => {
    const el = document.getElementById(String(id || ""));
    if (!(el instanceof HTMLInputElement)) return;
    const attached = attachShamsiField(el);
    if (attached) controllers.push(attached);
  });

  return {
    syncAll: () => {
      controllers.forEach((controller) => controller.syncFromSource());
    },
  };
}
