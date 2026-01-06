import type { AdminCreateUserRequest, AdminCreateUserResponse, TokenResponse, UserPublic } from "./types";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function jsonOrText(res: Response) {
  const contentType = res.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) return res.json();
  return res.text();
}

export async function apiLogin(email: string, password: string): Promise<TokenResponse> {
  const res = await fetch(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error(await jsonOrText(res));
  return (await res.json()) as TokenResponse;
}

export async function apiRefresh(refreshToken: string): Promise<TokenResponse> {
  const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!res.ok) throw new Error(await jsonOrText(res));
  return (await res.json()) as TokenResponse;
}

export async function apiLogout(refreshToken: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/auth/logout`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!res.ok) throw new Error(await jsonOrText(res));
}

export async function apiGetMe(accessToken: string): Promise<UserPublic> {
  const res = await fetch(`${API_BASE_URL}/me`, {
    headers: { authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) throw new Error(await jsonOrText(res));
  return (await res.json()) as UserPublic;
}

export async function apiAdminListUsers(accessToken: string): Promise<UserPublic[]> {
  const res = await fetch(`${API_BASE_URL}/admin/users`, {
    headers: { authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) throw new Error(await jsonOrText(res));
  return (await res.json()) as UserPublic[];
}

export async function apiAdminCreateUser(
  accessToken: string,
  payload: AdminCreateUserRequest
): Promise<AdminCreateUserResponse> {
  const res = await fetch(`${API_BASE_URL}/admin/users`, {
    method: "POST",
    headers: { authorization: `Bearer ${accessToken}`, "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await jsonOrText(res));
  return (await res.json()) as AdminCreateUserResponse;
}

