const SUSPECT_PATTERN =
  /[\u00c2\u00c3\u00d0\u00d8\u00d9\u00da\u00db]|\u00e2\u20ac|\u0152|\u0153|\u017e|\u2122|\u02dc/;

const CP1252_UNICODE_TO_BYTE: Record<number, number> = {
  8364: 0x80,
  8218: 0x82,
  402: 0x83,
  8222: 0x84,
  8230: 0x85,
  8224: 0x86,
  8225: 0x87,
  710: 0x88,
  8240: 0x89,
  352: 0x8a,
  8249: 0x8b,
  338: 0x8c,
  381: 0x8e,
  8216: 0x91,
  8217: 0x92,
  8220: 0x93,
  8221: 0x94,
  8226: 0x95,
  8211: 0x96,
  8212: 0x97,
  732: 0x98,
  8482: 0x99,
  353: 0x9a,
  8250: 0x9b,
  339: 0x9c,
  382: 0x9e,
  376: 0x9f,
};

const TEXT_ATTRS = ["placeholder", "title", "aria-label", "aria-description"];
const SKIP_TAGS = new Set(["SCRIPT", "STYLE", "NOSCRIPT"]);

const utf8Decoder =
  typeof TextDecoder !== "undefined"
    ? new TextDecoder("utf-8", { fatal: true })
    : null;

function isLikelyMojibake(input: string): boolean {
  return SUSPECT_PATTERN.test(input);
}

function charCodeToByte(code: number): number | null {
  if (code >= 0 && code <= 0xff) return code;
  return CP1252_UNICODE_TO_BYTE[code] ?? null;
}

function decodeLatinAsUtf8Once(input: string): string {
  if (!utf8Decoder || !input) return input;
  const bytes = new Uint8Array(input.length);
  let hasHighByte = false;

  for (let index = 0; index < input.length; index += 1) {
    const code = input.charCodeAt(index);
    const mapped = charCodeToByte(code);
    if (mapped == null) return input;
    bytes[index] = mapped;
    if (mapped >= 0x80) hasHighByte = true;
  }

  if (!hasHighByte) return input;

  try {
    const decoded = utf8Decoder.decode(bytes);
    if (!decoded || decoded.includes("\ufffd")) return input;
    return decoded;
  } catch {
    return input;
  }
}

export function repairMojibakeText(input: string): string {
  let value = String(input ?? "");
  if (!isLikelyMojibake(value)) return value;

  for (let pass = 0; pass < 4; pass += 1) {
    const decoded = decodeLatinAsUtf8Once(value);
    if (decoded === value) break;
    value = decoded;
    if (!isLikelyMojibake(value)) break;
  }

  return value;
}

function repairTextNode(node: Text): void {
  const value = node.nodeValue;
  if (!value || !isLikelyMojibake(value)) return;
  const repaired = repairMojibakeText(value);
  if (repaired !== value) node.nodeValue = repaired;
}

function repairElementAttrs(element: Element): void {
  TEXT_ATTRS.forEach((attrName) => {
    if (!element.hasAttribute(attrName)) return;
    const value = element.getAttribute(attrName);
    if (!value || !isLikelyMojibake(value)) return;
    const repaired = repairMojibakeText(value);
    if (repaired !== value) element.setAttribute(attrName, repaired);
  });
}

function repairDomSubtree(root: Node): void {
  const stack: Node[] = [root];

  while (stack.length) {
    const node = stack.pop();
    if (!node) continue;

    if (node.nodeType === Node.TEXT_NODE) {
      repairTextNode(node as Text);
      continue;
    }

    if (node.nodeType !== Node.ELEMENT_NODE) continue;

    const element = node as Element;
    if (SKIP_TAGS.has(element.tagName)) continue;

    repairElementAttrs(element);
    for (let index = element.childNodes.length - 1; index >= 0; index -= 1) {
      stack.push(element.childNodes[index]);
    }
  }
}

function patchUiMethods(): void {
  const ui = (window as any).UI;
  if (ui && typeof ui === "object" && !ui.__mojibakePatched) {
    ["success", "error", "warning", "info"].forEach((method) => {
      const original = ui[method];
      if (typeof original !== "function") return;
      ui[method] = (message: unknown, ...rest: unknown[]) =>
        original.call(ui, repairMojibakeText(String(message ?? "")), ...rest);
    });
    ui.__mojibakePatched = true;
  }

  const globalAny = window as any;
  if (typeof globalAny.showToast === "function" && !globalAny.__mojibakeToastPatched) {
    const originalToast = globalAny.showToast;
    globalAny.showToast = (message: unknown, ...rest: unknown[]) =>
      originalToast.call(window, repairMojibakeText(String(message ?? "")), ...rest);
    globalAny.__mojibakeToastPatched = true;
  }
}

function patchNativeDialogs(): void {
  const globalAny = window as any;
  if (globalAny.__mojibakeDialogPatched) return;

  const originalAlert = window.alert.bind(window);
  const originalConfirm = window.confirm.bind(window);

  window.alert = (message?: unknown) =>
    originalAlert(repairMojibakeText(String(message ?? "")));
  window.confirm = (message?: string) =>
    originalConfirm(repairMojibakeText(String(message ?? "")));

  globalAny.__mojibakeDialogPatched = true;
}

function observeDomMutations(): void {
  const observer = new MutationObserver((mutations) => {
    patchUiMethods();
    mutations.forEach((mutation) => {
      if (mutation.type === "characterData") {
        repairDomSubtree(mutation.target);
        return;
      }

      if (mutation.type === "attributes" && mutation.target) {
        repairDomSubtree(mutation.target);
        return;
      }

      mutation.addedNodes.forEach((node) => repairDomSubtree(node));
    });
  });

  observer.observe(document.documentElement, {
    subtree: true,
    childList: true,
    characterData: true,
    attributes: true,
    attributeFilter: TEXT_ATTRS,
  });
}

export function installMojibakeRuntimeFix(): void {
  const globalAny = window as any;
  if (globalAny.__mojibakeFixInstalled) return;
  globalAny.__mojibakeFixInstalled = true;

  patchNativeDialogs();

  const boot = () => {
    patchUiMethods();
    repairDomSubtree(document.documentElement);
    observeDomMutations();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
}
