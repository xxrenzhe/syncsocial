"use client";

import { useAuth } from "@/lib/auth";
import type { AdminSubscriptionOverview, AdminUpsertWorkspaceSubscriptionRequest, WorkspaceSubscriptionPublic } from "@/lib/types";
import { useEffect, useMemo, useState } from "react";

function toLocalDatetimeInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function fromLocalDatetimeInput(value: string): string | null {
  const raw = value.trim();
  if (!raw) return null;
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString();
}

function parseNullableInt(value: string): number | null {
  const raw = value.trim();
  if (!raw) return null;
  const n = Number.parseInt(raw, 10);
  if (!Number.isFinite(n)) return null;
  return n;
}

export default function AdminSubscriptionPage() {
  const auth = useAuth();
  const canView = useMemo(() => auth.user?.role === "admin", [auth.user?.role]);

  const [overview, setOverview] = useState<AdminSubscriptionOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [statusValue, setStatusValue] = useState("trial");
  const [planKey, setPlanKey] = useState("trial");
  const [seats, setSeats] = useState("1");
  const [maxSocialAccounts, setMaxSocialAccounts] = useState("");
  const [maxParallelSessions, setMaxParallelSessions] = useState("");
  const [automationRuntimeHours, setAutomationRuntimeHours] = useState("");
  const [artifactRetentionDays, setArtifactRetentionDays] = useState("");
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");

  function applyFromSubscription(sub: WorkspaceSubscriptionPublic | null) {
    setStatusValue(sub?.status ?? "trial");
    setPlanKey(sub?.plan_key ?? "trial");
    setSeats(String(sub?.seats ?? 1));
    setMaxSocialAccounts(sub?.max_social_accounts == null ? "" : String(sub.max_social_accounts));
    setMaxParallelSessions(sub?.max_parallel_sessions == null ? "" : String(sub.max_parallel_sessions));
    setAutomationRuntimeHours(sub?.automation_runtime_hours == null ? "" : String(sub.automation_runtime_hours));
    setArtifactRetentionDays(sub?.artifact_retention_days == null ? "" : String(sub.artifact_retention_days));
    setPeriodStart(toLocalDatetimeInput(sub?.current_period_start ?? null));
    setPeriodEnd(toLocalDatetimeInput(sub?.current_period_end ?? null));
  }

  async function load() {
    if (!canView) return;
    setLoading(true);
    setError(null);
    try {
      const res = await auth.apiFetch("/admin/subscription");
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as AdminSubscriptionOverview;
      setOverview(data);
      applyFromSubscription(data.subscription);
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

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const payload: AdminUpsertWorkspaceSubscriptionRequest = {
        status: statusValue,
        plan_key: planKey,
        seats: Number.parseInt(seats, 10) || 1,
        max_social_accounts: parseNullableInt(maxSocialAccounts),
        max_parallel_sessions: parseNullableInt(maxParallelSessions),
        automation_runtime_hours: parseNullableInt(automationRuntimeHours),
        artifact_retention_days: parseNullableInt(artifactRetentionDays),
        current_period_start: fromLocalDatetimeInput(periodStart),
        current_period_end: fromLocalDatetimeInput(periodEnd),
      };
      const res = await auth.apiFetch("/admin/subscription", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text());
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  if (!canView) {
    return (
      <div style={{ padding: 24 }}>
        <h1 style={{ marginBottom: 8 }}>订阅与配额</h1>
        <div style={{ opacity: 0.75 }}>无权限：仅管理员可访问。</div>
      </div>
    );
  }

  const usedSeconds = overview?.current_month_usage?.automation_runtime_seconds ?? 0;
  const usedHours = Math.round((usedSeconds / 3600) * 100) / 100;
  const quotaHours = overview?.subscription?.automation_runtime_hours ?? null;

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>订阅与配额</h1>
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

      <div style={{ display: "grid", gap: 10, marginBottom: 16 }}>
        <div style={{ opacity: 0.85 }}>
          <span style={{ opacity: 0.7 }}>当前状态：</span>
          {overview?.active ? "可用" : "不可用"}
          {overview?.active_reason ? `（${overview.active_reason}）` : ""}
        </div>
        <div style={{ opacity: 0.85 }}>
          <span style={{ opacity: 0.7 }}>本月运行时长：</span>
          {usedHours}h{quotaHours != null ? ` / ${quotaHours}h` : ""}
        </div>
      </div>

      <form onSubmit={save} style={{ display: "grid", gap: 12, maxWidth: 760 }}>
        <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 10, alignItems: "center" }}>
          <div style={{ opacity: 0.8 }}>status</div>
          <select value={statusValue} onChange={(e) => setStatusValue(e.target.value)} style={{ padding: 10, borderRadius: 8, border: "1px solid #333" }}>
            <option value="trial">trial</option>
            <option value="active">active</option>
            <option value="past_due">past_due</option>
            <option value="suspended">suspended</option>
            <option value="canceled">canceled</option>
          </select>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 10, alignItems: "center" }}>
          <div style={{ opacity: 0.8 }}>plan_key</div>
          <input value={planKey} onChange={(e) => setPlanKey(e.target.value)} style={{ padding: 10, borderRadius: 8, border: "1px solid #333" }} />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 10, alignItems: "center" }}>
          <div style={{ opacity: 0.8 }}>seats</div>
          <input
            value={seats}
            onChange={(e) => setSeats(e.target.value)}
            type="number"
            min={1}
            style={{ padding: 10, borderRadius: 8, border: "1px solid #333" }}
          />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 10, alignItems: "center" }}>
          <div style={{ opacity: 0.8 }}>max_social_accounts</div>
          <input
            value={maxSocialAccounts}
            onChange={(e) => setMaxSocialAccounts(e.target.value)}
            placeholder="留空=不限"
            type="number"
            min={0}
            style={{ padding: 10, borderRadius: 8, border: "1px solid #333" }}
          />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 10, alignItems: "center" }}>
          <div style={{ opacity: 0.8 }}>max_parallel_sessions</div>
          <input
            value={maxParallelSessions}
            onChange={(e) => setMaxParallelSessions(e.target.value)}
            placeholder="留空=不限（仍受 schedule.max_parallel 影响）"
            type="number"
            min={0}
            style={{ padding: 10, borderRadius: 8, border: "1px solid #333" }}
          />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 10, alignItems: "center" }}>
          <div style={{ opacity: 0.8 }}>automation_runtime_hours</div>
          <input
            value={automationRuntimeHours}
            onChange={(e) => setAutomationRuntimeHours(e.target.value)}
            placeholder="留空=不限"
            type="number"
            min={0}
            style={{ padding: 10, borderRadius: 8, border: "1px solid #333" }}
          />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 10, alignItems: "center" }}>
          <div style={{ opacity: 0.8 }}>artifact_retention_days</div>
          <input
            value={artifactRetentionDays}
            onChange={(e) => setArtifactRetentionDays(e.target.value)}
            placeholder="留空=不限制（MVP 暂不做清理任务）"
            type="number"
            min={0}
            style={{ padding: 10, borderRadius: 8, border: "1px solid #333" }}
          />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 10, alignItems: "center" }}>
          <div style={{ opacity: 0.8 }}>current_period_start</div>
          <input value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} type="datetime-local" style={{ padding: 10, borderRadius: 8, border: "1px solid #333" }} />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 10, alignItems: "center" }}>
          <div style={{ opacity: 0.8 }}>current_period_end</div>
          <input value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} type="datetime-local" style={{ padding: 10, borderRadius: 8, border: "1px solid #333" }} />
        </div>

        <button
          type="submit"
          disabled={saving}
          style={{
            padding: "10px 14px",
            borderRadius: 10,
            border: "none",
            background: saving ? "#3a3a3a" : "#2f6fed",
            color: "white",
          }}
        >
          {saving ? "保存中…" : "保存订阅"}
        </button>
      </form>
    </div>
  );
}

