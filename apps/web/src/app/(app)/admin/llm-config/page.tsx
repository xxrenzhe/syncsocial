"use client";

import { useAuth } from "@/lib/auth";
import type { WorkspaceLlmConfigPublic } from "@/lib/types";
import { useEffect, useMemo, useState } from "react";

export default function AdminLlmConfigPage() {
  const auth = useAuth();
  const canView = useMemo(() => auth.user?.role === "admin", [auth.user?.role]);

  const [config, setConfig] = useState<WorkspaceLlmConfigPublic | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [provider, setProvider] = useState("openai");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("gpt-4o-mini");
  const [apiKey, setApiKey] = useState("");

  function applyFromConfig(row: WorkspaceLlmConfigPublic | null) {
    setConfig(row);
    setProvider(row?.provider || "openai");
    setBaseUrl(row?.base_url || "");
    setModel(row?.model || "gpt-4o-mini");
    setApiKey("");
  }

  async function load() {
    if (!canView) return;
    setLoading(true);
    setError(null);
    try {
      const res = await auth.apiFetch("/admin/llm-config");
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as WorkspaceLlmConfigPublic | null;
      applyFromConfig(data);
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
    if (!apiKey.trim()) {
      setError("api_key 不能为空");
      return;
    }
    setSaving(true);
    try {
      const res = await auth.apiFetch("/admin/llm-config", {
        method: "PUT",
        body: JSON.stringify({
          provider,
          api_key: apiKey.trim(),
          base_url: baseUrl.trim() || null,
          model: model.trim() || null,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as WorkspaceLlmConfigPublic;
      applyFromConfig(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  if (!canView) {
    return (
      <div style={{ padding: 24 }}>
        <h1 style={{ marginBottom: 8 }}>LLM 配置</h1>
        <div style={{ opacity: 0.75 }}>无权限：仅管理员可访问。</div>
      </div>
    );
  }

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>LLM 配置</h1>
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
          {config ? `已配置（${config.provider}${config.model ? ` / ${config.model}` : ""}）` : "未配置"}
        </div>
        <div style={{ opacity: 0.85 }}>
          <span style={{ opacity: 0.7 }}>API Key：</span>
          {config?.has_api_key ? "已设置（不可查看）" : "未设置"}
        </div>
      </div>

      <form onSubmit={save} style={{ display: "grid", gap: 12, maxWidth: 760 }}>
        <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 10, alignItems: "center" }}>
          <div style={{ opacity: 0.8 }}>provider</div>
          <select value={provider} onChange={(e) => setProvider(e.target.value)} style={{ padding: 10, borderRadius: 8, border: "1px solid #333" }}>
            <option value="openai">openai</option>
          </select>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 10, alignItems: "center" }}>
          <div style={{ opacity: 0.8 }}>base_url</div>
          <input
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="留空=默认 https://api.openai.com/v1"
            style={{ padding: 10, borderRadius: 8, border: "1px solid #333" }}
          />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 10, alignItems: "center" }}>
          <div style={{ opacity: 0.8 }}>model</div>
          <input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="留空=默认 gpt-4o-mini"
            style={{ padding: 10, borderRadius: 8, border: "1px solid #333" }}
          />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 10, alignItems: "center" }}>
          <div style={{ opacity: 0.8 }}>api_key</div>
          <input
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            type="password"
            placeholder={config?.has_api_key ? "重新填写以更新/覆盖" : "填写 OpenAI API Key"}
            style={{ padding: 10, borderRadius: 8, border: "1px solid #333" }}
          />
        </div>

        <button
          type="submit"
          disabled={saving}
          style={{
            padding: "10px 14px",
            borderRadius: 10,
            border: "none",
            background: saving ? "#555" : "#2f6fed",
            color: "white",
            width: 140,
          }}
        >
          {saving ? "保存中…" : "保存"}
        </button>
      </form>
    </div>
  );
}

