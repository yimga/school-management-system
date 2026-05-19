export type CommandBarResultType =
  | 'navigate'
  | 'documentation'
  | 'locked'
  | 'escalate';

export interface CommandBarResult {
  type: CommandBarResultType;
  label: string;
  path_label?: string;
  detail?: string;
  url?: string | null;
  missing_permission?: string;
  locked?: boolean;
  icon?: string;
}

export interface CommandBarSearchResponse {
  success: boolean;
  results: CommandBarResult[];
  permissions?: string[];
}
