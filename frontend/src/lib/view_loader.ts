export interface ViewLoaderScriptDeps {
  isScriptLoaded: (absoluteSrc: string) => boolean;
  markScriptLoaded: (absoluteSrc: string) => void;
}

export interface FetchPartialResult {
  ok: boolean;
  status: number;
  html: string | null;
}

export interface ViewLoaderPartialDeps extends ViewLoaderScriptDeps {
  resolvePartialName: (viewId: string) => string | null | undefined;
  isViewCached: (viewId: string) => boolean;
  markViewCached: (viewId: string) => void;
  getViewHost: (viewId: string) => HTMLElement | null;
  markPerf: (name: string) => void;
  measurePerf: (metricName: string, startMark: string, endMark: string) => void;
  fetchPartialHtml: (partialName: string) => Promise<FetchPartialResult>;
  emitViewLoaded: (viewId: string, partialName: string) => void;
  showToast: (message: string, type?: string) => void;
}

export interface ViewLoaderBridge {
  executeScriptsInElement(rootElement: Element | null, deps: ViewLoaderScriptDeps): Promise<boolean>;
  loadViewPartial(viewId: string, deps: ViewLoaderPartialDeps): Promise<boolean>;
}

function normalize(input: unknown): string {
  return String(input || "").trim();
}

async function executeScriptsInElement(
  rootElement: Element | null,
  deps: ViewLoaderScriptDeps
): Promise<boolean> {
  if (!rootElement) return false;

  const scripts = Array.from(rootElement.querySelectorAll("script"));
  for (const oldScript of scripts) {
    const newScript = document.createElement("script");
    for (const attr of Array.from(oldScript.attributes || [])) {
      newScript.setAttribute(attr.name, attr.value);
    }

    const srcAttr = oldScript.getAttribute("src");
    if (srcAttr) {
      const absoluteSrc = new URL(srcAttr, window.location.origin).href;
      if (deps.isScriptLoaded(absoluteSrc)) {
        oldScript.remove();
        continue;
      }

      await new Promise<void>((resolve, reject) => {
        newScript.onload = () => resolve();
        newScript.onerror = () => reject(new Error(`Failed to load script: ${srcAttr}`));
        oldScript.replaceWith(newScript);
      });
      deps.markScriptLoaded(absoluteSrc);
      continue;
    }

    newScript.textContent = oldScript.textContent || "";
    oldScript.replaceWith(newScript);
  }

  return true;
}

async function loadViewPartial(viewId: string, deps: ViewLoaderPartialDeps): Promise<boolean> {
  const normalizedViewId = normalize(viewId);
  if (!normalizedViewId) return false;

  const partialName = normalize(deps.resolvePartialName(normalizedViewId));
  if (!partialName) return true;
  if (deps.isViewCached(normalizedViewId)) return true;

  const host = deps.getViewHost(normalizedViewId);
  if (!host) return false;

  host.innerHTML = '<div class="lazy-view-state">در حال بارگذاری صفحه...</div>';
  const metricKey = `partial_${partialName}`;
  deps.markPerf(`${metricKey}_start`);

  try {
    const result = await deps.fetchPartialHtml(partialName);
    if (!result.ok || !result.html) {
      throw new Error(`Failed to load view (${result.status})`);
    }

    const wrapper = document.createElement("div");
    wrapper.innerHTML = result.html;
    const incomingView = (wrapper.querySelector(`#${normalizedViewId}`) ||
      wrapper.querySelector(".view-section")) as HTMLElement | null;
    if (!incomingView) {
      throw new Error(`Invalid partial payload for ${normalizedViewId}`);
    }

    host.replaceWith(incomingView);
    await executeScriptsInElement(incomingView, deps);
    deps.markViewCached(normalizedViewId);
    deps.markPerf(`${metricKey}_end`);
    deps.measurePerf(metricKey, `${metricKey}_start`, `${metricKey}_end`);
    deps.emitViewLoaded(normalizedViewId, partialName);
    return true;
  } catch (error) {
    const errorHost = deps.getViewHost(normalizedViewId) || host;
    errorHost.innerHTML = `
      <div class="lazy-view-state">
        خطا در بارگذاری صفحه.
        <button type="button" class="btn-archive-icon" data-nav-target="${normalizedViewId}">تلاش مجدد</button>
      </div>
    `;
    deps.showToast("بارگذاری صفحه با خطا مواجه شد.", "error");
    console.error(error);
    return false;
  }
}

export function createViewLoaderBridge(): ViewLoaderBridge {
  return {
    executeScriptsInElement,
    loadViewPartial,
  };
}

