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

