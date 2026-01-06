"use client";

import { useAuth } from "@/lib/auth";
import type { RunPublic, SchedulePublic, StrategyPublic } from "@/lib/types";
import Link from "next/link";
import { useEffect, useState } from "react";

export default function SchedulesPage() {
  const auth = useAuth();
  const [strategies, setStrategies] = useState<StrategyPublic[]>([]);
  const [schedules, setSchedules] = useState<SchedulePublic[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [strategyId, setStrategyId] = useState("");
  const [accountSelectorText, setAccountSelectorText] = useState('{"all": true}');

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [sRes, cRes] = await Promise.all([auth.apiFetch("/strategies"), auth.apiFetch("/schedules")]);
      if (!sRes.ok) throw new Error(await sRes.text());
      if (!cRes.ok) throw new Error(await cRes.text());
      const sData = (await sRes.json()) as StrategyPublic[];
      const cData = (await cRes.json()) as SchedulePublic[];
      setStrategies(sData);
      setSchedules(cData);
      if (!strategyId && sData[0]?.id) setStrategyId(sData[0].id);
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

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!strategyId) {
      setError("请先创建策略");
      return;
    }
    let selector: Record<string, unknown> = {};
    try {
      selector = JSON.parse(accountSelectorText) as Record<string, unknown>;
    } catch {
      setError("account_selector 必须是合法 JSON");
      return;
    }
    try {
      const res = await auth.apiFetch("/schedules", {
        method: "POST",
        body: JSON.stringify({
          name,
          strategy_id: strategyId,
          enabled: true,
          account_selector: selector,
          frequency: "manual",
          schedule_spec: {},
          random_config: {},
          max_parallel: 1,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      setName("");
      setAccountSelectorText('{"all": true}');
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建失败");
    }
  }

  async function runNow(schedule: SchedulePublic) {
    setError(null);
    try {
      const res = await auth.apiFetch(`/schedules/${schedule.id}/run-now`, { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      const run = (await res.json()) as RunPublic;
      await load();
      window.alert(`已触发 Run: ${run.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "触发失败");
    }
  }

  return (
    <div style={{ padding: 24 }}>
      <h1 style={{ marginBottom: 16 }}>执行计划</h1>

      <form onSubmit={create} style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="计划名称"
          required
          style={{ padding: 10, borderRadius: 8, border: "1px solid #333", minWidth: 220 }}
        />
        <select
          value={strategyId}
          onChange={(e) => setStrategyId(e.target.value)}
          style={{ padding: 10, borderRadius: 8, border: "1px solid #333", minWidth: 260 }}
        >
          {strategies.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name} ({s.platform_key} v{s.version})
            </option>
          ))}
        </select>
        <input
          value={accountSelectorText}
          onChange={(e) => setAccountSelectorText(e.target.value)}
          placeholder='account_selector JSON，比如 {"all": true}'
          style={{ padding: 10, borderRadius: 8, border: "1px solid #333", minWidth: 360 }}
        />
        <button
          type="submit"
          style={{ padding: "10px 14px", borderRadius: 10, border: "none", background: "#2f6fed", color: "white" }}
        >
          创建计划
        </button>
        <Link href="/runs" style={{ padding: "10px 14px", borderRadius: 10, border: "1px solid #333" }}>
          查看运行记录
        </Link>
      </form>

      {error ? <div style={{ color: "#ff6b6b", marginBottom: 12 }}>{error}</div> : null}
      {loading ? <div style={{ opacity: 0.8, marginBottom: 12 }}>加载中…</div> : null}

      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #333" }}>
              <th style={{ padding: 10 }}>Name</th>
              <th style={{ padding: 10 }}>Enabled</th>
              <th style={{ padding: 10 }}>Strategy</th>
              <th style={{ padding: 10 }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {schedules.map((s) => (
              <tr key={s.id} style={{ borderBottom: "1px solid #222" }}>
                <td style={{ padding: 10 }}>{s.name}</td>
                <td style={{ padding: 10 }}>{s.enabled ? "yes" : "no"}</td>
                <td style={{ padding: 10 }}>{s.strategy_id}</td>
                <td style={{ padding: 10 }}>
                  <button
                    type="button"
                    onClick={() => runNow(s)}
                    style={{ padding: "6px 10px", borderRadius: 8, border: "1px solid #333", background: "transparent" }}
                  >
                    立即运行
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

