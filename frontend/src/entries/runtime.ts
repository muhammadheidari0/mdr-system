import { createAppShellBridge } from "../lib/app_shell";
import { createAppBootBridge } from "../lib/app_boot";
import { createAppRouterBridge } from "../lib/app_router";
import { createEdmsStateBridge } from "../lib/edms_state";
import { createModuleBoardBridge } from "../lib/module_board";
import { createModuleTabsBridge } from "../lib/module_tabs";
import { createViewLoaderBridge } from "../lib/view_loader";
import { createAppDataBridge } from "../lib/app_data";
import { createTransmittalUiBridge } from "../lib/transmittal_ui";
import { createTransmittalDataBridge } from "../lib/transmittal_data";
import { createTransmittalMutationsBridge } from "../lib/transmittal_mutations";
import { createCorrespondenceDataBridge } from "../lib/correspondence_data";
import { createCorrespondenceMutationsBridge } from "../lib/correspondence_mutations";
import { createCorrespondenceUiBridge } from "../lib/correspondence_ui";
import { createCorrespondenceStateBridge } from "../lib/correspondence_state";
import { createCorrespondenceFormBridge } from "../lib/correspondence_form";
import { createCorrespondenceWorkflowBridge } from "../lib/correspondence_workflow";
import { createCommItemsDataBridge } from "../lib/comm_items_data";
import { createCommItemsFormBridge } from "../lib/comm_items_form";
import { createCommItemsStateBridge } from "../lib/comm_items_state";
import { createCommItemsUiBridge } from "../lib/comm_items_ui";
import { createCommItemsWorkflowBridge } from "../lib/comm_items_workflow";
import { createSiteLogsDataBridge } from "../lib/site_logs_data";
import { createSiteLogsFormBridge } from "../lib/site_logs_form";
import { createSiteLogsStateBridge } from "../lib/site_logs_state";
import { createSiteLogsUiBridge } from "../lib/site_logs_ui";
import { installMojibakeRuntimeFix } from "../lib/mojibake_fix";

window.AppRuntime = {
  appShell: createAppShellBridge(),
  appBoot: createAppBootBridge(),
  appRouter: createAppRouterBridge(),
  edmsState: createEdmsStateBridge(),
  moduleBoard: createModuleBoardBridge(),
  moduleTabs: createModuleTabsBridge(),
  viewLoader: createViewLoaderBridge(),
  appData: createAppDataBridge(),
  transmittalUi: createTransmittalUiBridge(),
  transmittalData: createTransmittalDataBridge(),
  transmittalMutations: createTransmittalMutationsBridge(),
  correspondenceData: createCorrespondenceDataBridge(),
  correspondenceMutations: createCorrespondenceMutationsBridge(),
  correspondenceUi: createCorrespondenceUiBridge(),
  correspondenceState: createCorrespondenceStateBridge(),
  correspondenceForm: createCorrespondenceFormBridge(),
  correspondenceWorkflow: createCorrespondenceWorkflowBridge(),
  commItemsData: createCommItemsDataBridge(),
  commItemsForm: createCommItemsFormBridge(),
  commItemsState: createCommItemsStateBridge(),
  commItemsUi: createCommItemsUiBridge(),
  commItemsWorkflow: createCommItemsWorkflowBridge(),
  siteLogsData: createSiteLogsDataBridge(),
  siteLogsForm: createSiteLogsFormBridge(),
  siteLogsState: createSiteLogsStateBridge(),
  siteLogsUi: createSiteLogsUiBridge(),
};

installMojibakeRuntimeFix();
