import type { AppShellBridge } from "./lib/app_shell";
import type { AppBootBridge } from "./lib/app_boot";
import type { AppRouterBridge } from "./lib/app_router";
import type { EdmsStateBridge } from "./lib/edms_state";
import type { ModuleBoardBridge } from "./lib/module_board";
import type { ModuleTabsBridge } from "./lib/module_tabs";
import type { ViewLoaderBridge } from "./lib/view_loader";
import type { AppDataBridge } from "./lib/app_data";
import type { TransmittalUiBridge } from "./lib/transmittal_ui";
import type { TransmittalDataBridge } from "./lib/transmittal_data";
import type { TransmittalMutationsBridge } from "./lib/transmittal_mutations";
import type { CorrespondenceDataBridge } from "./lib/correspondence_data";
import type { CorrespondenceMutationsBridge } from "./lib/correspondence_mutations";
import type { CorrespondenceUiBridge } from "./lib/correspondence_ui";
import type { CorrespondenceStateBridge } from "./lib/correspondence_state";
import type { CorrespondenceFormBridge } from "./lib/correspondence_form";
import type { CorrespondenceWorkflowBridge } from "./lib/correspondence_workflow";

export {};

declare global {
  interface AppRuntime {
    appShell: AppShellBridge;
    appBoot: AppBootBridge;
    appRouter: AppRouterBridge;
    edmsState: EdmsStateBridge;
    moduleBoard: ModuleBoardBridge;
    moduleTabs: ModuleTabsBridge;
    viewLoader: ViewLoaderBridge;
    appData: AppDataBridge;
    transmittalUi: TransmittalUiBridge;
    transmittalData: TransmittalDataBridge;
    transmittalMutations: TransmittalMutationsBridge;
    correspondenceData: CorrespondenceDataBridge;
    correspondenceMutations: CorrespondenceMutationsBridge;
    correspondenceUi: CorrespondenceUiBridge;
    correspondenceState: CorrespondenceStateBridge;
    correspondenceForm: CorrespondenceFormBridge;
    correspondenceWorkflow: CorrespondenceWorkflowBridge;
  }

  interface Window {
    AppRuntime?: AppRuntime;
    [key: string]: unknown;
  }
}
