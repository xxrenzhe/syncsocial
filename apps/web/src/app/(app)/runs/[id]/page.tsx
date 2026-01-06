"use client";

import { useAuth } from "@/lib/auth";
import type { ActionPublic, RunDetail } from "@/lib/types";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

export default function RunDetailPage() {
  const auth = useAuth();
  const params = useParams<{ id: string }>();
  const runId = params.id;

  const [data, setData] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await auth.apiFetch(`/runs/${runId}`);
      if (!res.ok) throw new Error(await res.text());
      const json = (await res.json()) as RunDetail;
      setData(json);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  function getMetaString(action: ActionPublic, key: string) {
    const v = action.metadata[key];
    return typeof v === "string" ? v : null;
  }

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 16 }}>
        <Link href="/runs" style={{ padding: "6px 10px", borderRadius: 8, border: "1px solid #333" }}>
          返回
        </Link>
        <h1 style={{ margin: 0 }}>Run 详情</h1>
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

      {data ? (
        <>
          <div style={{ marginBottom: 16, opacity: 0.85 }}>
            <div>
              <span style={{ opacity: 0.7 }}>Status：</span>
              {data.run.status}
            </div>
            <div>
              <span style={{ opacity: 0.7 }}>Created：</span>
              {new Date(data.run.created_at).toLocaleString()}
            </div>
          </div>

          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "1px solid #333" }}>
                  <th style={{ padding: 10 }}>AccountRun</th>
                  <th style={{ padding: 10 }}>SocialAccount</th>
                  <th style={{ padding: 10 }}>Status</th>
                  <th style={{ padding: 10 }}>Error</th>
                </tr>
              </thead>
              <tbody>
                {data.account_runs.map((ar) => (
                  <tr key={ar.id} style={{ borderBottom: "1px solid #222" }}>
                    <td style={{ padding: 10, fontFamily: "monospace" }}>{ar.id}</td>
                    <td style={{ padding: 10, fontFamily: "monospace" }}>{ar.social_account_id}</td>
                    <td style={{ padding: 10 }}>{ar.status}</td>
                    <td style={{ padding: 10 }}>{ar.error_code || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h2 style={{ marginTop: 24, marginBottom: 12 }}>Actions</h2>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "1px solid #333" }}>
                  <th style={{ padding: 10 }}>Action</th>
                  <th style={{ padding: 10 }}>AccountRun</th>
                  <th style={{ padding: 10 }}>Status</th>
                  <th style={{ padding: 10 }}>Error</th>
                  <th style={{ padding: 10 }}>Target</th>
                  <th style={{ padding: 10 }}>Message</th>
                </tr>
              </thead>
              <tbody>
                {data.actions.map((a) => (
                  <tr key={a.id} style={{ borderBottom: "1px solid #222" }}>
                    <td style={{ padding: 10 }}>{a.action_type}</td>
                    <td style={{ padding: 10, fontFamily: "monospace" }}>{a.account_run_id}</td>
                    <td style={{ padding: 10 }}>{a.status}</td>
                    <td style={{ padding: 10 }}>{a.error_code || "—"}</td>
                    <td style={{ padding: 10 }}>
                      {a.target_url ? (
                        <a href={a.target_url} target="_blank" rel="noreferrer">
                          打开
                        </a>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td style={{ padding: 10, opacity: 0.8 }}>{getMetaString(a, "message") || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </div>
  );
}
