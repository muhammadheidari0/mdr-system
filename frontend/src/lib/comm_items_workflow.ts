export interface CommItemsWorkflowTransition {
  item_type?: string;
  from_status_code?: string;
  to_status_code?: string;
  requires_note?: boolean;
}

export interface CommItemsWorkflowBridge {
  key(itemType: unknown, fromStatus: unknown): string;
  normalize(value: unknown): string;
  buildMap(transitions: CommItemsWorkflowTransition[] | null | undefined): Map<string, CommItemsWorkflowTransition[]>;
  nextStatuses(
    itemType: unknown,
    fromStatus: unknown,
    map: Map<string, CommItemsWorkflowTransition[]>
  ): CommItemsWorkflowTransition[];
  requiresNote(itemType: unknown, fromStatus: unknown, toStatus: unknown, map: Map<string, CommItemsWorkflowTransition[]>): boolean;
  canUseReviewResult(statusCode: unknown): boolean;
}

function normalize(value: unknown): string {
  return String(value ?? "").trim().toUpperCase();
}

function key(itemType: unknown, fromStatus: unknown): string {
  return `${normalize(itemType)}:${normalize(fromStatus)}`;
}

function buildMap(
  transitions: CommItemsWorkflowTransition[] | null | undefined
): Map<string, CommItemsWorkflowTransition[]> {
  const map = new Map<string, CommItemsWorkflowTransition[]>();
  (transitions || []).forEach((row) => {
    const rowKey = key(row.item_type, row.from_status_code);
    if (!rowKey || rowKey === ":") return;
    if (!map.has(rowKey)) map.set(rowKey, []);
    map.get(rowKey)?.push(row);
  });
  return map;
}

function nextStatuses(
  itemType: unknown,
  fromStatus: unknown,
  map: Map<string, CommItemsWorkflowTransition[]>
): CommItemsWorkflowTransition[] {
  return map.get(key(itemType, fromStatus)) || [];
}

function requiresNote(
  itemType: unknown,
  fromStatus: unknown,
  toStatus: unknown,
  map: Map<string, CommItemsWorkflowTransition[]>
): boolean {
  const target = normalize(toStatus);
  const rows = nextStatuses(itemType, fromStatus, map);
  return rows.some((row) => normalize(row.to_status_code) === target && Boolean(row.requires_note));
}

function canUseReviewResult(statusCode: unknown): boolean {
  const status = normalize(statusCode);
  return ["IN_REVIEW", "APPROVED", "APPROVED_AS_NOTED", "REVISE_RESUBMIT", "REJECTED", "CLOSED"].includes(status);
}

export function createCommItemsWorkflowBridge(): CommItemsWorkflowBridge {
  return {
    key,
    normalize,
    buildMap,
    nextStatuses,
    requiresNote,
    canUseReviewResult,
  };
}
