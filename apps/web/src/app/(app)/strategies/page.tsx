"use client";

import { useAuth } from "@/lib/auth";
import type { StrategyPublic } from "@/lib/types";
import { useEffect, useMemo, useState } from "react";

export default function StrategiesPage() {
  const auth = useAuth();
  const [strategies, setStrategies] = useState<StrategyPublic[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const platformOptions = useMemo(
    () => [
      { value: "x", label: "X（Twitter）" },
      { value: "reddit", label: "Reddit（预留）" },
      { value: "facebook", label: "Facebook（预留）" },
      { value: "instagram", label: "Instagram（预留）" },
    ],
    []
  );

  const [name, setName] = useState("");
  const [platformKey, setPlatformKey] = useState("x");
  const [configText, setConfigText] = useState("{}");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await auth.apiFetch("/strategies");
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as StrategyPublic[];
      setStrategies(data);
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
    let config: Record<string, unknown> = {};
    try {
      config = JSON.parse(configText) as Record<string, unknown>;
    } catch {
      setError("config 必须是合法 JSON");
      return;
    }
    try {
      const res = await auth.apiFetch("/strategies", {
        method: "POST",
        body: JSON.stringify({ name, platform_key: platformKey, config }),
      });
      if (!res.ok) throw new Error(await res.text());
      setName("");
      setConfigText("{}");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建失败");
    }
  }

  return (
    <div style={{ padding: 24 }}>
      <h1 style={{ marginBottom: 16 }}>策略中心</h1>

      <form onSubmit={create} style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="策略名称"
          required
          style={{ padding: 10, borderRadius: 8, border: "1px solid #333", minWidth: 220 }}
        />
        <select
          value={platformKey}
          onChange={(e) => setPlatformKey(e.target.value)}
          style={{ padding: 10, borderRadius: 8, border: "1px solid #333" }}
        >
          {platformOptions.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </select>
        <input
          value={configText}
          onChange={(e) => setConfigText(e.target.value)}
          placeholder='config JSON，比如 {"key":"value"}'
          style={{ padding: 10, borderRadius: 8, border: "1px solid #333", minWidth: 360 }}
        />
        <button
          type="submit"
          style={{ padding: "10px 14px", borderRadius: 10, border: "none", background: "#2f6fed", color: "white" }}
        >
          创建策略
        </button>
      </form>

      {error ? <div style={{ color: "#ff6b6b", marginBottom: 12 }}>{error}</div> : null}
      {loading ? <div style={{ opacity: 0.8, marginBottom: 12 }}>加载中…</div> : null}

      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #333" }}>
              <th style={{ padding: 10 }}>Name</th>
              <th style={{ padding: 10 }}>Platform</th>
              <th style={{ padding: 10 }}>Version</th>
              <th style={{ padding: 10 }}>Updated</th>
            </tr>
          </thead>
          <tbody>
            {strategies.map((s) => (
              <tr key={s.id} style={{ borderBottom: "1px solid #222" }}>
                <td style={{ padding: 10 }}>{s.name}</td>
                <td style={{ padding: 10 }}>{s.platform_key}</td>
                <td style={{ padding: 10 }}>{s.version}</td>
                <td style={{ padding: 10 }}>{new Date(s.updated_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

