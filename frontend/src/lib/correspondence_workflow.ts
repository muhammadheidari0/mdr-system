import { createCorrespondenceDataBridge } from "./correspondence_data";
import {
  type CorrespondenceAttachmentDownloadResult,
  createCorrespondenceMutationsBridge,
  type CorrespondenceActionPayload,
  type CorrespondencePreviewResult,
  type CorrespondenceSavePayload,
} from "./correspondence_mutations";

export interface CorrespondenceWorkflowHttpDeps {
  fetch: (url: string, init?: RequestInit) => Promise<Response>;
}

export interface CorrespondenceWorkflowListResult {
  ok: boolean;
  detail?: string;
  data: Record<string, unknown>[];
}

export interface CorrespondenceWorkflowMutationResult {
  ok: boolean;
  detail?: string;
  data?: Record<string, unknown>;
}

export interface CorrespondenceWorkflowOpenDeps {
  openEdit: (id: number) => Promise<void> | void;
  scrollToActions: () => void;
}

export interface CorrespondenceWorkflowAfterActionDeps {
  correspondenceId: number;
  clearActionEditor?: () => Promise<void> | void;
  loadActions: (id: number) => Promise<void> | void;
  loadDashboard: () => Promise<void> | void;
  loadList: () => Promise<void> | void;
}

export interface CorrespondenceWorkflowAfterAttachmentDeps {
  correspondenceId: number;
  loadAttachments: (id: number) => Promise<void> | void;
  loadDashboard: () => Promise<void> | void;
  loadList: () => Promise<void> | void;
}

export interface CorrespondenceWorkflowBridge {
  loadActions(
    correspondenceId: number,
    deps: CorrespondenceWorkflowHttpDeps
  ): Promise<CorrespondenceWorkflowListResult>;
  loadAttachments(
    correspondenceId: number,
    deps: CorrespondenceWorkflowHttpDeps
  ): Promise<CorrespondenceWorkflowListResult>;
  openWorkflow(correspondenceId: number, deps: CorrespondenceWorkflowOpenDeps): Promise<boolean>;
  saveCorrespondence(
    correspondenceId: number,
    payload: CorrespondenceSavePayload,
    deps: CorrespondenceWorkflowHttpDeps
  ): Promise<CorrespondenceWorkflowMutationResult>;
  upsertAction(
    correspondenceId: number,
    actionId: number,
    payload: CorrespondenceActionPayload,
    deps: CorrespondenceWorkflowHttpDeps
  ): Promise<CorrespondenceWorkflowMutationResult>;
  toggleActionClosed(
    actionId: number,
    checked: boolean,
    deps: CorrespondenceWorkflowHttpDeps
  ): Promise<CorrespondenceWorkflowMutationResult>;
  deleteAction(
    actionId: number,
    deps: CorrespondenceWorkflowHttpDeps
  ): Promise<CorrespondenceWorkflowMutationResult>;
  uploadAttachment(
    correspondenceId: number,
    formData: FormData,
    deps: CorrespondenceWorkflowHttpDeps
  ): Promise<CorrespondenceWorkflowMutationResult>;
  deleteAttachment(
    attachmentId: number,
    deps: CorrespondenceWorkflowHttpDeps
  ): Promise<CorrespondenceWorkflowMutationResult>;
  downloadAttachment(
    attachmentId: number,
    deps: CorrespondenceWorkflowHttpDeps
  ): Promise<CorrespondenceAttachmentDownloadResult>;
  previewCorrespondence(
    correspondenceId: number,
    deps: CorrespondenceWorkflowHttpDeps
  ): Promise<CorrespondencePreviewResult>;
  deleteCorrespondence(
    correspondenceId: number,
    deps: CorrespondenceWorkflowHttpDeps
  ): Promise<CorrespondenceWorkflowMutationResult>;
  afterActionMutation(deps: CorrespondenceWorkflowAfterActionDeps): Promise<boolean>;
  afterAttachmentMutation(deps: CorrespondenceWorkflowAfterAttachmentDeps): Promise<boolean>;
}

const dataBridge = createCorrespondenceDataBridge();
const mutationBridge = createCorrespondenceMutationsBridge();

function asRecord(input: unknown): Record<string, unknown> {
  if (input && typeof input === "object") {
    return input as Record<string, unknown>;
  }
  return {};
}

function asMessage(error: unknown, fallback: string): string {
  if (error instanceof Error) {
    const msg = String(error.message || "").trim();
    if (msg) return msg;
  }
  return fallback;
}

function toMutationResult(
  body: Record<string, unknown>,
  fallbackOk: boolean
): CorrespondenceWorkflowMutationResult {
  const ok = typeof body.ok === "boolean" ? body.ok : fallbackOk;
  const detailRaw = String(body.detail || "").trim();
  const dataRaw = body.data;
  const data =
    dataRaw && typeof dataRaw === "object"
      ? (dataRaw as Record<string, unknown>)
      : undefined;
  return {
    ok,
    detail: detailRaw || undefined,
    data,
  };
}

async function loadActions(
  correspondenceId: number,
  deps: CorrespondenceWorkflowHttpDeps
): Promise<CorrespondenceWorkflowListResult> {
  try {
    const body = asRecord(await dataBridge.listActions(correspondenceId, deps));
    if (!body.ok) {
      return {
        ok: false,
        detail: String(body.detail || "Failed to load actions."),
        data: [],
      };
    }
    return {
      ok: true,
      data: Array.isArray(body.data) ? (body.data as Record<string, unknown>[]) : [],
    };
  } catch (error) {
    return {
      ok: false,
      detail: asMessage(error, "Failed to load actions."),
      data: [],
    };
  }
}

async function loadAttachments(
  correspondenceId: number,
  deps: CorrespondenceWorkflowHttpDeps
): Promise<CorrespondenceWorkflowListResult> {
  try {
    const body = asRecord(await dataBridge.listAttachments(correspondenceId, deps));
    if (!body.ok) {
      return {
        ok: false,
        detail: String(body.detail || "Failed to load attachments."),
        data: [],
      };
    }
    return {
      ok: true,
      data: Array.isArray(body.data) ? (body.data as Record<string, unknown>[]) : [],
    };
  } catch (error) {
    return {
      ok: false,
      detail: asMessage(error, "Failed to load attachments."),
      data: [],
    };
  }
}

async function openWorkflow(
  correspondenceId: number,
  deps: CorrespondenceWorkflowOpenDeps
): Promise<boolean> {
  await Promise.resolve(deps.openEdit(Number(correspondenceId) || 0));
  deps.scrollToActions();
  return true;
}

async function saveCorrespondence(
  correspondenceId: number,
  payload: CorrespondenceSavePayload,
  deps: CorrespondenceWorkflowHttpDeps
): Promise<CorrespondenceWorkflowMutationResult> {
  try {
    const body = asRecord(
      await mutationBridge.saveCorrespondence(correspondenceId, payload, deps)
    );
    return toMutationResult(body, true);
  } catch (error) {
    return {
      ok: false,
      detail: asMessage(error, "Failed to save correspondence."),
    };
  }
}

async function upsertAction(
  correspondenceId: number,
  actionId: number,
  payload: CorrespondenceActionPayload,
  deps: CorrespondenceWorkflowHttpDeps
): Promise<CorrespondenceWorkflowMutationResult> {
  try {
    const body = asRecord(
      await mutationBridge.upsertAction(correspondenceId, actionId, payload, deps)
    );
    return toMutationResult(body, true);
  } catch (error) {
    return {
      ok: false,
      detail: asMessage(error, "Failed to save action."),
    };
  }
}

async function toggleActionClosed(
  actionId: number,
  checked: boolean,
  deps: CorrespondenceWorkflowHttpDeps
): Promise<CorrespondenceWorkflowMutationResult> {
  try {
    const body = asRecord(
      await mutationBridge.toggleActionClosed(actionId, checked, deps)
    );
    return toMutationResult(body, true);
  } catch (error) {
    return {
      ok: false,
      detail: asMessage(error, "Failed to update action status."),
    };
  }
}

async function deleteAction(
  actionId: number,
  deps: CorrespondenceWorkflowHttpDeps
): Promise<CorrespondenceWorkflowMutationResult> {
  try {
    const body = asRecord(await mutationBridge.deleteAction(actionId, deps));
    return toMutationResult(body, true);
  } catch (error) {
    return {
      ok: false,
      detail: asMessage(error, "Failed to delete action."),
    };
  }
}

async function uploadAttachment(
  correspondenceId: number,
  formData: FormData,
  deps: CorrespondenceWorkflowHttpDeps
): Promise<CorrespondenceWorkflowMutationResult> {
  try {
    const body = asRecord(
      await mutationBridge.uploadAttachment(correspondenceId, formData, deps)
    );
    return toMutationResult(body, true);
  } catch (error) {
    return {
      ok: false,
      detail: asMessage(error, "Failed to upload attachment."),
    };
  }
}

async function deleteAttachment(
  attachmentId: number,
  deps: CorrespondenceWorkflowHttpDeps
): Promise<CorrespondenceWorkflowMutationResult> {
  try {
    const body = asRecord(
      await mutationBridge.deleteAttachment(attachmentId, deps)
    );
    return toMutationResult(body, true);
  } catch (error) {
    return {
      ok: false,
      detail: asMessage(error, "Failed to delete attachment."),
    };
  }
}

async function downloadAttachment(
  attachmentId: number,
  deps: CorrespondenceWorkflowHttpDeps
): Promise<CorrespondenceAttachmentDownloadResult> {
  return mutationBridge.downloadAttachment(attachmentId, deps);
}

async function previewCorrespondence(
  correspondenceId: number,
  deps: CorrespondenceWorkflowHttpDeps
): Promise<CorrespondencePreviewResult> {
  return mutationBridge.previewCorrespondence(correspondenceId, deps);
}

async function deleteCorrespondence(
  correspondenceId: number,
  deps: CorrespondenceWorkflowHttpDeps
): Promise<CorrespondenceWorkflowMutationResult> {
  try {
    const body = asRecord(await mutationBridge.deleteCorrespondence(correspondenceId, deps));
    return toMutationResult(body, true);
  } catch (error) {
    return {
      ok: false,
      detail: asMessage(error, "Failed to delete correspondence."),
    };
  }
}

async function afterActionMutation(
  deps: CorrespondenceWorkflowAfterActionDeps
): Promise<boolean> {
  const id = Number(deps.correspondenceId) || 0;
  if (deps.clearActionEditor) {
    await Promise.resolve(deps.clearActionEditor());
  }
  await Promise.resolve(deps.loadActions(id));
  await Promise.resolve(deps.loadDashboard());
  await Promise.resolve(deps.loadList());
  return true;
}

async function afterAttachmentMutation(
  deps: CorrespondenceWorkflowAfterAttachmentDeps
): Promise<boolean> {
  const id = Number(deps.correspondenceId) || 0;
  await Promise.resolve(deps.loadAttachments(id));
  await Promise.resolve(deps.loadDashboard());
  await Promise.resolve(deps.loadList());
  return true;
}

export function createCorrespondenceWorkflowBridge(): CorrespondenceWorkflowBridge {
  return {
    loadActions,
    loadAttachments,
    openWorkflow,
    saveCorrespondence,
    upsertAction,
    toggleActionClosed,
    deleteAction,
    uploadAttachment,
    deleteAttachment,
    downloadAttachment,
    previewCorrespondence,
    deleteCorrespondence,
    afterActionMutation,
    afterAttachmentMutation,
  };
}
