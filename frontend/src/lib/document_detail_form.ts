// @ts-nocheck
const EDITABLE_FIELDS = [
  "subject",
  "notes",
];

export function sanitizeMetadataDraft(input: Record<string, unknown>) {
  const out: Record<string, unknown> = {};
  for (const key of EDITABLE_FIELDS) {
    if (!(key in (input || {}))) continue;
    const value = (input || {})[key];
    if (typeof value === "string") {
      out[key] = value.trim();
      continue;
    }
    out[key] = value ?? null;
  }
  return out;
}

export function validateMetadataPayload(payload: Record<string, unknown>) {
  const clean = sanitizeMetadataDraft(payload || {});
  if (!Object.keys(clean).length) {
    return { ok: false, errors: ["هیچ فیلدی برای ذخیره وجود ندارد."], payload: clean };
  }
  return { ok: true, errors: [], payload: clean };
}
