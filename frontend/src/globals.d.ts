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
import type { CommItemsDataBridge } from "./lib/comm_items_data";
import type { CommItemsFormBridge } from "./lib/comm_items_form";
import type { CommItemsStateBridge } from "./lib/comm_items_state";
import type { CommItemsUiBridge } from "./lib/comm_items_ui";
import type { CommItemsWorkflowBridge } from "./lib/comm_items_workflow";
import type { SiteLogsDataBridge } from "./lib/site_logs_data";
import type { SiteLogsFormBridge } from "./lib/site_logs_form";
import type { SiteLogsStateBridge } from "./lib/site_logs_state";
import type { SiteLogsUiBridge } from "./lib/site_logs_ui";

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
    commItemsData: CommItemsDataBridge;
    commItemsForm: CommItemsFormBridge;
    commItemsState: CommItemsStateBridge;
    commItemsUi: CommItemsUiBridge;
    commItemsWorkflow: CommItemsWorkflowBridge;
    siteLogsData: SiteLogsDataBridge;
    siteLogsForm: SiteLogsFormBridge;
    siteLogsState: SiteLogsStateBridge;
    siteLogsUi: SiteLogsUiBridge;
  }

  interface Window {
    AppRuntime?: AppRuntime;
    [key: string]: unknown;
  }
}
