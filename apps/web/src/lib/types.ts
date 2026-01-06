export type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  access_token_expires_at: string;
};

export type UserPublic = {
  id: string;
  workspace_id: string;
  email: string;
  display_name: string | null;
  role: "admin" | "user" | string;
  status: "active" | "disabled" | "deleted" | string;
  must_change_password: boolean;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
};

export type AdminCreateUserRequest = {
  email: string;
  role: "admin" | "user";
  display_name?: string | null;
  temporary_password?: string | null;
};

export type AdminCreateUserResponse = {
  user: UserPublic;
  initial_password?: string | null;
};

export type WorkspaceSubscriptionPublic = {
  id: string;
  workspace_id: string;
  status: string;
  plan_key: string;
  seats: number;
  max_social_accounts: number | null;
  max_parallel_sessions: number | null;
  automation_runtime_hours: number | null;
  artifact_retention_days: number | null;
  current_period_start: string | null;
  current_period_end: string | null;
  created_at: string;
  updated_at: string;
};

export type WorkspaceUsageMonthlyPublic = {
  id: string;
  workspace_id: string;
  period_start: string;
  automation_runtime_seconds: number;
  created_at: string;
  updated_at: string;
};

export type AdminUpsertWorkspaceSubscriptionRequest = {
  status: string;
  plan_key: string;
  seats: number;
  max_social_accounts?: number | null;
  max_parallel_sessions?: number | null;
  automation_runtime_hours?: number | null;
  artifact_retention_days?: number | null;
  current_period_start?: string | null;
  current_period_end?: string | null;
};

export type AdminSubscriptionOverview = {
  subscription: WorkspaceSubscriptionPublic | null;
  current_month_usage: WorkspaceUsageMonthlyPublic | null;
  active: boolean;
  active_reason: string | null;
};

export type AuditLogPublic = {
  id: string;
  workspace_id: string;
  actor_user_id: string | null;
  actor_email: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type SocialAccountPublic = {
  id: string;
  workspace_id: string;
  platform_key: string;
  handle: string | null;
  display_name: string | null;
  status: string;
  labels: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  last_health_check_at: string | null;
};

export type LoginSessionPublic = {
  id: string;
  workspace_id: string;
  social_account_id: string;
  platform_key: string;
  status: string;
  remote_url: string | null;
  expires_at: string;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};

export type StrategyPublic = {
  id: string;
  workspace_id: string;
  name: string;
  platform_key: string;
  version: number;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type SchedulePublic = {
  id: string;
  workspace_id: string;
  name: string;
  enabled: boolean;
  strategy_id: string;
  account_selector: Record<string, unknown>;
  frequency: string;
  schedule_spec: Record<string, unknown>;
  random_config: Record<string, unknown>;
  max_parallel: number;
  next_run_at: string | null;
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
};

export type RunPublic = {
  id: string;
  workspace_id: string;
  schedule_id: string | null;
  strategy_id: string;
  triggered_by: string | null;
  status: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type AccountRunPublic = {
  id: string;
  workspace_id: string;
  run_id: string;
  social_account_id: string;
  status: string;
  error_code: string | null;
  started_at: string | null;
  finished_at: string | null;
};

export type ActionPublic = {
  id: string;
  workspace_id: string;
  account_run_id: string;
  action_type: string;
  platform_key: string;
  target_external_id: string | null;
  target_url: string | null;
  idempotency_key: string;
  status: string;
  error_code: string | null;
  metadata: Record<string, unknown>;
  artifacts: ArtifactPublic[];
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type ArtifactPublic = {
  id: string;
  workspace_id: string;
  action_id: string;
  type: string;
  storage_key: string;
  size: number | null;
  created_at: string;
};

export type RunDetail = {
  run: RunPublic;
  account_runs: AccountRunPublic[];
  actions: ActionPublic[];
};
