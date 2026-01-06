"use client";

import { useAuth } from "@/lib/auth";
import type { AdminCreateUserResponse, UserPublic } from "@/lib/types";
import { useEffect, useMemo, useState } from "react";

export default function AdminUsersPage() {
  const auth = useAuth();
  const [users, setUsers] = useState<UserPublic[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canView = useMemo(() => auth.user?.role === "admin", [auth.user?.role]);

  const [createEmail, setCreateEmail] = useState("");
  const [createRole, setCreateRole] = useState<"user" | "admin">("user");
  const [createDisplayName, setCreateDisplayName] = useState("");

  async function loadUsers() {
    if (!canView) return;
    setLoading(true);
    setError(null);
    try {
      const res = await auth.apiFetch("/admin/users");
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as UserPublic[];
      setUsers(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadUsers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canView]);

  async function createUser(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const res = await auth.apiFetch("/admin/users", {
        method: "POST",
        body: JSON.stringify({
          email: createEmail,
          role: createRole,
          display_name: createDisplayName || null,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as AdminCreateUserResponse;
      if (data.initial_password) {
        window.alert(`用户已创建，临时密码：${data.initial_password}`);
      }
      setCreateEmail("");
      setCreateDisplayName("");
      await loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建失败");
    }
  }

  async function toggleStatus(user: UserPublic) {
    const nextStatus = user.status === "active" ? "disabled" : "active";
    const res = await auth.apiFetch(`/admin/users/${user.id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: nextStatus }),
    });
    if (!res.ok) throw new Error(await res.text());
    await loadUsers();
  }

  async function resetPassword(user: UserPublic) {
    const res = await auth.apiFetch(`/admin/users/${user.id}/reset-password`, { method: "POST" });
    if (!res.ok) throw new Error(await res.text());
    const data = (await res.json()) as { temporary_password: string };
    window.alert(`临时密码：${data.temporary_password}`);
    await loadUsers();
  }

  async function deleteUser(user: UserPublic) {
    const ok = window.confirm(`确认删除用户 ${user.email} ?`);
    if (!ok) return;
    const res = await auth.apiFetch(`/admin/users/${user.id}`, { method: "DELETE" });
    if (!res.ok) throw new Error(await res.text());
    await loadUsers();
  }

  if (!canView) {
    return (
      <div style={{ padding: 24 }}>
        <h1 style={{ marginBottom: 8 }}>用户管理</h1>
        <div style={{ opacity: 0.75 }}>无权限：仅管理员可访问。</div>
      </div>
    );
  }

  return (
    <div style={{ padding: 24 }}>
      <h1 style={{ marginBottom: 16 }}>用户管理</h1>

      <form onSubmit={createUser} style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
        <input
          value={createEmail}
          onChange={(e) => setCreateEmail(e.target.value)}
          type="email"
          placeholder="email"
          required
          style={{ padding: 10, borderRadius: 8, border: "1px solid #333", minWidth: 260 }}
        />
        <input
          value={createDisplayName}
          onChange={(e) => setCreateDisplayName(e.target.value)}
          placeholder="display_name（可选）"
          style={{ padding: 10, borderRadius: 8, border: "1px solid #333", minWidth: 220 }}
        />
        <select
          value={createRole}
          onChange={(e) => setCreateRole(e.target.value as "user" | "admin")}
          style={{ padding: 10, borderRadius: 8, border: "1px solid #333" }}
        >
          <option value="user">user</option>
          <option value="admin">admin</option>
        </select>
        <button
          type="submit"
          style={{ padding: "10px 14px", borderRadius: 10, border: "none", background: "#2f6fed", color: "white" }}
        >
          创建用户
        </button>
      </form>

      {error ? <div style={{ color: "#ff6b6b", marginBottom: 12 }}>{error}</div> : null}
      {loading ? <div style={{ opacity: 0.8, marginBottom: 12 }}>加载中…</div> : null}

      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #333" }}>
              <th style={{ padding: 10 }}>Email</th>
              <th style={{ padding: 10 }}>Role</th>
              <th style={{ padding: 10 }}>Status</th>
              <th style={{ padding: 10 }}>Must Change</th>
              <th style={{ padding: 10 }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} style={{ borderBottom: "1px solid #222" }}>
                <td style={{ padding: 10 }}>{u.email}</td>
                <td style={{ padding: 10 }}>{u.role}</td>
                <td style={{ padding: 10 }}>{u.status}</td>
                <td style={{ padding: 10 }}>{u.must_change_password ? "yes" : "no"}</td>
                <td style={{ padding: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <button
                    type="button"
                    onClick={() => toggleStatus(u).catch((e) => setError(String(e)))}
                    style={{ padding: "6px 10px", borderRadius: 8, border: "1px solid #333", background: "transparent" }}
                  >
                    {u.status === "active" ? "禁用" : "启用"}
                  </button>
                  <button
                    type="button"
                    onClick={() => resetPassword(u).catch((e) => setError(String(e)))}
                    style={{ padding: "6px 10px", borderRadius: 8, border: "1px solid #333", background: "transparent" }}
                  >
                    重置密码
                  </button>
                  <button
                    type="button"
                    onClick={() => deleteUser(u).catch((e) => setError(String(e)))}
                    style={{
                      padding: "6px 10px",
                      borderRadius: 8,
                      border: "1px solid #ff6b6b",
                      background: "transparent",
                      color: "#ff6b6b",
                    }}
                  >
                    删除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

