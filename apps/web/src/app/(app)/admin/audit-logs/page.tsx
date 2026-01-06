"use client";

import { useAuth } from "@/lib/auth";
import type { AuditLogPublic } from "@/lib/types";
import { useEffect, useMemo, useState } from "react";

function formatMeta(meta: Record<string, unknown>): string {
  try {
    return JSON.stringify(meta, null, 2);
  } catch {
    return String(meta);
  }
}

export default function AdminAuditLogsPage() {
  const auth = useAuth();
  const canView = useMemo(() => auth.user?.role === "admin", [auth.user?.role]);

  const [logs, setLogs] = useState<AuditLogPublic[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    if (!canView) return;
    setLoading(true);
    setError(null);
    try {
      const res = await auth.apiFetch("/admin/audit-logs?limit=300");
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as AuditLogPublic[];
      setLogs(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canView]);

  if (!canView) {
    return (
      <div style={{ padding: 24 }}>
        <h1 style={{ marginBottom: 8 }}>审计日志</h1>
        <div style={{ opacity: 0.75 }}>无权限：仅管理员可访问。</div>
      </div>
    );
  }

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>审计日志</h1>
        <button
          type="button"
          onClick={() => load().catch(() => null)}
          style={{ marginLeft: "auto", padding: "6px 10px", borderRadius: 8, border: "1px solid #333", background: "transparent" }}
        >
          刷新
        </button>
      </div>

      {error ? <div style={{ color: "#ff6b6b", marginBottom: 12 }}>{error}</div> : null}
      {loading ? <div style={{ opacity: 0.8, marginBottom: 12 }}>加载中…</div> : null}

      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #333" }}>
              <th style={{ padding: 10 }}>Time</th>
              <th style={{ padding: 10 }}>Actor</th>
              <th style={{ padding: 10 }}>Action</th>
              <th style={{ padding: 10 }}>Target</th>
              <th style={{ padding: 10 }}>Metadata</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((l) => (
              <tr key={l.id} style={{ borderBottom: "1px solid #222", verticalAlign: "top" }}>
                <td style={{ padding: 10, whiteSpace: "nowrap" }}>{new Date(l.created_at).toLocaleString()}</td>
                <td style={{ padding: 10 }}>{l.actor_email || l.actor_user_id || "—"}</td>
                <td style={{ padding: 10, fontFamily: "monospace" }}>{l.action}</td>
                <td style={{ padding: 10, fontFamily: "monospace" }}>
                  {l.target_type ? `${l.target_type}:${l.target_id || "—"}` : "—"}
                </td>
                <td style={{ padding: 10 }}>
                  <button
                    type="button"
                    onClick={() => window.alert(formatMeta(l.metadata))}
                    style={{ padding: "6px 10px", borderRadius: 8, border: "1px solid #333", background: "transparent" }}
                  >
                    查看
                  </button>
                </td>
              </tr>
            ))}
            {!logs.length && !loading ? (
              <tr>
                <td style={{ padding: 10, opacity: 0.7 }} colSpan={5}>
                  暂无记录
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}

