export interface ModuleTabMap {
  [tabName: string]: string;
}

export interface ModuleTabsInitialTab {
  tabName: string;
  button: HTMLElement | null;
}

export interface ModuleTabsBridge {
  switchTab(
    tabName: string,
    tabToPanelMap: ModuleTabMap,
    tabButtonSelector: string,
    dataAttrName: string,
    btnEl?: Element | null
  ): string | null;
  resolveInitialTab(
    tabButtonSelector: string,
    dataAttrName: string,
    defaultTab: string
  ): ModuleTabsInitialTab;
}

function normalize(input: unknown): string {
  return String(input || "").trim().toLowerCase();
}

function safeQuerySelector(selector: string): HTMLElement | null {
  try {
    return document.querySelector(selector) as HTMLElement | null;
  } catch {
    return null;
  }
}

function switchTab(
  tabName: string,
  tabToPanelMap: ModuleTabMap,
  tabButtonSelector: string,
  dataAttrName: string,
  btnEl?: Element | null
): string | null {
  const normalized = normalize(tabName);
  if (!normalized || !tabToPanelMap || !tabToPanelMap[normalized]) return null;

  Object.entries(tabToPanelMap).forEach(([tab, panelId]) => {
    const panel = document.getElementById(panelId);
    if (!panel) return;
    const active = normalize(tab) === normalized;
    panel.style.display = active ? "block" : "none";
    panel.classList.toggle("active", active);
  });

  document.querySelectorAll(tabButtonSelector).forEach((button) => {
    (button as HTMLElement).classList.remove("active");
  });

  const targetSelector = `${tabButtonSelector}[${dataAttrName}="${normalized}"]`;
  const button = (btnEl as HTMLElement | null) || safeQuerySelector(targetSelector);
  if (button) {
    button.classList.add("active");
  }

  return normalized;
}

function resolveInitialTab(
  tabButtonSelector: string,
  dataAttrName: string,
  defaultTab: string
): ModuleTabsInitialTab {
  const currentButton = safeQuerySelector(`${tabButtonSelector}.active`);
  const normalizedDefault = normalize(defaultTab);

  if (!currentButton) {
    return {
      tabName: normalizedDefault,
      button: null,
    };
  }

  const attrName = String(dataAttrName || "")
    .trim()
    .replace(/^data-/, "")
    .replace(/-([a-z])/g, (_m, letter: string) => letter.toUpperCase());
  const fromDataSet = attrName ? currentButton.dataset[attrName] : "";
  const tabName = normalize(fromDataSet) || normalizedDefault;
  return {
    tabName,
    button: currentButton,
  };
}

export function createModuleTabsBridge(): ModuleTabsBridge {
  return {
    switchTab,
    resolveInitialTab,
  };
}
