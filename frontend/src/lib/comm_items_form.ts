export type CommItemType = "RFI" | "NCR";

export interface CommItemsFormInput {
  itemType?: unknown;
  moduleKey?: unknown;
  tabKey?: unknown;
  projectCode?: unknown;
  disciplineCode?: unknown;
  zone?: unknown;
  title?: unknown;
  shortDescription?: unknown;
  statusCode?: unknown;
  priority?: unknown;
  responseDueDate?: unknown;
  organizationId?: unknown;
  recipientOrgId?: unknown;
  assigneeUserId?: unknown;
  contractClauseRef?: unknown;
  specClauseRef?: unknown;
  wbsCode?: unknown;
  activityCode?: unknown;
  impactTime?: unknown;
  impactCost?: unknown;
  impactQuality?: unknown;
  impactSafety?: unknown;
  impactNote?: unknown;
  delayDaysEstimate?: unknown;
  costEstimate?: unknown;
  claimNoticeRequired?: unknown;
  noticeDeadline?: unknown;
  rfiQuestionText?: unknown;
  rfiProposedSolution?: unknown;
  rfiAnswerText?: unknown;
  rfiAnsweredAt?: unknown;
  rfiDrawingRefs?: unknown;
  rfiSpecRefs?: unknown;
  ncrKind?: unknown;
  ncrSeverity?: unknown;
  ncrNonconformanceText?: unknown;
  ncrContainmentAction?: unknown;
  ncrRectificationMethod?: unknown;
  ncrVerificationNote?: unknown;
  ncrVerifiedAt?: unknown;
}

export interface CommItemsFormDefaults {
  itemType: CommItemType;
  priority: string;
  statusCode: string;
  techSubtypeCode: string;
}

export interface CommItemsFormBridge {
  resolveItemType(input: { itemType?: unknown; moduleKey?: unknown; tabKey?: unknown }): CommItemType;
  resolveDefaultTechSubtype(moduleKey: unknown, tabKey: unknown): string;
  defaultValues(moduleKey: unknown, tabKey: unknown, explicitItemType?: unknown): CommItemsFormDefaults;
  toIsoDate(value: unknown): string | null;
  toInt(value: unknown): number | null;
  toFloat(value: unknown): number | null;
  toBool(value: unknown): boolean;
  parseRefs(value: unknown): string[];
  validateForSubmit(input: CommItemsFormInput): string[];
  buildCreatePayload(input: CommItemsFormInput): Record<string, unknown>;
  buildUpdatePayload(input: CommItemsFormInput): Record<string, unknown>;
}

function trimString(value: unknown): string {
  return String(value ?? "").trim();
}

function upperString(value: unknown): string {
  return trimString(value).toUpperCase();
}

function normalizeModule(value: unknown): string {
  return trimString(value).toLowerCase();
}

function resolveItemType(input: { itemType?: unknown; moduleKey?: unknown; tabKey?: unknown }): CommItemType {
  const explicit = upperString(input.itemType);
  if (explicit === "RFI" || explicit === "NCR") {
    return explicit;
  }

  const moduleKey = normalizeModule(input.moduleKey);
  const tabKey = normalizeModule(input.tabKey);
  const mapping: Record<string, CommItemType> = {
    "contractor:requests": "RFI",
    "consultant:defects": "NCR",
  };

  return mapping[`${moduleKey}:${tabKey}`] || "RFI";
}

function resolveDefaultTechSubtype(moduleKey: unknown, tabKey: unknown): string {
  const moduleValue = normalizeModule(moduleKey);
  const tabValue = normalizeModule(tabKey);
  if (moduleValue === "consultant" && tabValue === "instructions") return "INSTRUCTION";
  if (moduleValue === "consultant" && tabValue === "inspection") return "IR";
  if (moduleValue === "contractor" && tabValue === "execution") return "SUBMITTAL";
  return "SUBMITTAL";
}

function defaultStatusForType(itemType: CommItemType): string {
  if (itemType === "NCR") return "ISSUED";
  return "DRAFT";
}

function defaultValues(moduleKey: unknown, tabKey: unknown, explicitItemType?: unknown): CommItemsFormDefaults {
  const itemType = resolveItemType({ itemType: explicitItemType, moduleKey, tabKey });
  return {
    itemType,
    priority: "NORMAL",
    statusCode: defaultStatusForType(itemType),
    techSubtypeCode: resolveDefaultTechSubtype(moduleKey, tabKey),
  };
}

function toIsoDate(value: unknown): string | null {
  const raw = trimString(value);
  if (!raw) return null;
  if (raw.includes("T")) return raw;
  return `${raw}T00:00:00`;
}

function toInt(value: unknown): number | null {
  const raw = trimString(value);
  if (!raw) return null;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return null;
  const integer = Math.trunc(parsed);
  return integer > 0 ? integer : null;
}

function toFloat(value: unknown): number | null {
  const raw = trimString(value);
  if (!raw) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

function toBool(value: unknown): boolean {
  if (typeof value === "boolean") return value;
  const normalized = trimString(value).toLowerCase();
  return ["1", "true", "yes", "on"].includes(normalized);
}

function parseRefs(value: unknown): string[] {
  const raw = trimString(value);
  if (!raw) return [];
  const tokens = raw
    .split(/[\n,;]+/g)
    .map((v) => trimString(v))
    .filter((v) => !!v);
  return Array.from(new Set(tokens));
}

function validateForSubmit(input: CommItemsFormInput): string[] {
  const errors: string[] = [];
  const itemType = resolveItemType({
    itemType: input.itemType,
    moduleKey: input.moduleKey,
    tabKey: input.tabKey,
  });
  const statusCode = upperString(input.statusCode) || defaultStatusForType(itemType);

  if (!upperString(input.projectCode)) errors.push("Project is required.");
  if (!upperString(input.disciplineCode)) errors.push("Discipline is required.");
  if (trimString(input.title).length < 5) errors.push("Title must be at least 5 characters.");

  if (itemType === "RFI") {
    if (statusCode === "SUBMITTED") {
      if (trimString(input.rfiQuestionText).length < 20) errors.push("RFI question must be at least 20 characters.");
      if (!toInt(input.recipientOrgId)) errors.push("Recipient org is required for RFI SUBMITTED.");
      if (!toIsoDate(input.responseDueDate)) errors.push("Response due date is required for RFI SUBMITTED.");
    }
    if (statusCode === "ANSWERED") {
      if (!trimString(input.rfiAnswerText)) errors.push("RFI answer_text is required for ANSWERED.");
      if (!toIsoDate(input.rfiAnsweredAt)) errors.push("RFI answered_at is required for ANSWERED.");
    }
  }

  if (itemType === "NCR") {
    if (statusCode === "ISSUED") {
      if (!upperString(input.ncrKind)) errors.push("NCR kind is required for ISSUED.");
      if (!upperString(input.ncrSeverity)) errors.push("NCR severity is required for ISSUED.");
      if (trimString(input.ncrNonconformanceText).length < 20) {
        errors.push("NCR nonconformance text must be at least 20 characters.");
      }
    }
    if (statusCode === "CONTRACTOR_REPLY" && !trimString(input.ncrRectificationMethod)) {
      errors.push("NCR rectification method is required for CONTRACTOR_REPLY.");
    }
    if (["VERIFIED", "CLOSED"].includes(statusCode)) {
      if (!trimString(input.ncrVerificationNote)) errors.push("NCR verification note is required.");
      if (!toIsoDate(input.ncrVerifiedAt)) errors.push("NCR verified_at is required.");
    }
  }

  return errors;
}

function basePayload(input: CommItemsFormInput): Record<string, unknown> {
  const itemType = resolveItemType({
    itemType: input.itemType,
    moduleKey: input.moduleKey,
    tabKey: input.tabKey,
  });
  return {
    item_type: itemType,
    project_code: upperString(input.projectCode),
    discipline_code: upperString(input.disciplineCode),
    zone: trimString(input.zone) || null,
    title: trimString(input.title),
    short_description: trimString(input.shortDescription) || null,
    status_code: upperString(input.statusCode) || defaultStatusForType(itemType),
    priority: upperString(input.priority) || "NORMAL",
    response_due_date: toIsoDate(input.responseDueDate),
    organization_id: toInt(input.organizationId),
    recipient_org_id: toInt(input.recipientOrgId),
    assignee_user_id: toInt(input.assigneeUserId),
    contract_clause_ref: trimString(input.contractClauseRef) || null,
    spec_clause_ref: trimString(input.specClauseRef) || null,
    wbs_code: trimString(input.wbsCode) || null,
    activity_code: trimString(input.activityCode) || null,
    potential_impact_time: toBool(input.impactTime),
    potential_impact_cost: toBool(input.impactCost),
    potential_impact_quality: false,
    potential_impact_safety: false,
    impact_note: null,
    delay_days_estimate: null,
    cost_estimate: null,
    claim_notice_required: false,
    notice_deadline: null,
  };
}

function buildCreatePayload(input: CommItemsFormInput): Record<string, unknown> {
  const payload = basePayload(input);
  const itemType = String(payload.item_type || "RFI") as CommItemType;

  if (itemType === "RFI") {
    payload.rfi = {
      question_text: trimString(input.rfiQuestionText),
      proposed_solution: trimString(input.rfiProposedSolution) || null,
      answer_text: trimString(input.rfiAnswerText) || null,
      answered_at: toIsoDate(input.rfiAnsweredAt),
      drawing_refs: parseRefs(input.rfiDrawingRefs),
      spec_refs: parseRefs(input.rfiSpecRefs),
    };
  }

  if (itemType === "NCR") {
    payload.ncr = {
      kind: upperString(input.ncrKind) || "NCR",
      severity: upperString(input.ncrSeverity) || "MINOR",
      nonconformance_text: trimString(input.ncrNonconformanceText),
      containment_action: trimString(input.ncrContainmentAction) || null,
      rectification_method: trimString(input.ncrRectificationMethod) || null,
      verification_note: trimString(input.ncrVerificationNote) || null,
      verified_at: toIsoDate(input.ncrVerifiedAt),
    };
  }

  return payload;
}

function buildUpdatePayload(input: CommItemsFormInput): Record<string, unknown> {
  const payload = buildCreatePayload(input);
  delete payload.item_type;
  if (!trimString(input.projectCode)) delete payload.project_code;
  if (!trimString(input.disciplineCode)) delete payload.discipline_code;
  return payload;
}

export function createCommItemsFormBridge(): CommItemsFormBridge {
  return {
    resolveItemType,
    resolveDefaultTechSubtype,
    defaultValues,
    toIsoDate,
    toInt,
    toFloat,
    toBool,
    parseRefs,
    validateForSubmit,
    buildCreatePayload,
    buildUpdatePayload,
  };
}
