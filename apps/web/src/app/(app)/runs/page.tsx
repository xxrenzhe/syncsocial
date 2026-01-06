"use client";

import { useAuth } from "@/lib/auth";
import type { RunPublic } from "@/lib/types";
import Link from "next/link";
import { useEffect, useState } from "react";

export default function RunsPage() {
  const auth = useAuth();
  const [runs, setRuns] = useState<RunPublic[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await auth.apiFetch("/runs");
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as RunPublic[];
      setRuns(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div style={{ padding: 24 }}>
      <h1 style={{ marginBottom: 16 }}>运行记录</h1>
      <div style={{ marginBottom: 16, display: "flex", gap: 12 }}>
        <button
          type="button"
          onClick={() => load().catch(() => null)}
          style={{ padding: "10px 14px", borderRadius: 10, border: "1px solid #333", background: "transparent" }}
        >
          刷新
        </button>
        <Link href="/schedules" style={{ padding: "10px 14px", borderRadius: 10, border: "1px solid #333" }}>
          去执行计划
        </Link>
      </div>

      {error ? <div style={{ color: "#ff6b6b", marginBottom: 12 }}>{error}</div> : null}
      {loading ? <div style={{ opacity: 0.8, marginBottom: 12 }}>加载中…</div> : null}

      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #333" }}>
              <th style={{ padding: 10 }}>Run</th>
              <th style={{ padding: 10 }}>Status</th>
              <th style={{ padding: 10 }}>Created</th>
              <th style={{ padding: 10 }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id} style={{ borderBottom: "1px solid #222" }}>
                <td style={{ padding: 10, fontFamily: "monospace" }}>{r.id}</td>
                <td style={{ padding: 10 }}>{r.status}</td>
                <td style={{ padding: 10 }}>{new Date(r.created_at).toLocaleString()}</td>
                <td style={{ padding: 10 }}>
                  <Link href={`/runs/${r.id}`} style={{ padding: "6px 10px", borderRadius: 8, border: "1px solid #333" }}>
                    详情
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

