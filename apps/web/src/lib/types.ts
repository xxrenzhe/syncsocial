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
