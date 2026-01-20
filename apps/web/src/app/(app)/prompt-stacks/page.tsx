"use client";

import { useAuth } from "@/lib/auth";
import type { PromptStackPublic } from "@/lib/types";
import { useEffect, useMemo, useState } from "react";

export default function PromptStacksPage() {
  const auth = useAuth();
  const [stacks, setStacks] = useState<PromptStackPublic[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [key, setKey] = useState("");
  const [payloadText, setPayloadText] = useState("{}");
  const [seed, setSeed] = useState<string>("");
  const [preview, setPreview] = useState<string>("");

  const keys = useMemo(() => stacks.map((s) => s.key), [stacks]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await auth.apiFetch("/prompt-stacks");
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as PromptStackPublic[];
      setStacks(data);
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

  function applyExisting(selectedKey: string) {
    const stack = stacks.find((s) => s.key === selectedKey);
    if (!stack) return;
    setKey(stack.key);
    setPayloadText(JSON.stringify(stack.payload ?? {}, null, 2));
    setPreview("");
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPreview("");
    const normalizedKey = key.trim();
    if (!normalizedKey) {
      setError("key 不能为空");
      return;
    }

    let payload: Record<string, unknown> = {};
    try {
      payload = JSON.parse(payloadText) as Record<string, unknown>;
    } catch {
      setError("payload 必须是合法 JSON");
      return;
    }

    try {
      const res = await auth.apiFetch(`/prompt-stacks/${encodeURIComponent(normalizedKey)}`, {
        method: "PUT",
        body: JSON.stringify({ payload }),
      });
      if (!res.ok) throw new Error(await res.text());
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    }
  }

  async function doPreview() {
    setError(null);
    setPreview("");
    const normalizedKey = key.trim();
    if (!normalizedKey) {
      setError("key 不能为空");
      return;
    }

    let payload: Record<string, unknown> = {};
    try {
      payload = JSON.parse(payloadText) as Record<string, unknown>;
    } catch {
      setError("payload 必须是合法 JSON");
      return;
    }

    const seedValue = seed.trim() ? Number(seed.trim()) : null;
    if (seedValue !== null && Number.isNaN(seedValue)) {
      setError("seed 必须是数字或留空");
      return;
    }

    try {
      const res = await auth.apiFetch(`/prompt-stacks/${encodeURIComponent(normalizedKey)}/preview`, {
        method: "POST",
        body: JSON.stringify({ payload, seed: seedValue }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as { text: string };
      setPreview(data.text);
    } catch (err) {
      setError(err instanceof Error ? err.message : "预览失败");
    }
  }

  return (
    <div style={{ padding: 24 }}>
      <h1 style={{ marginBottom: 16 }}>提示词堆叠</h1>

      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginBottom: 16 }}>
        <select
          value=""
          onChange={(e) => {
            const selected = e.target.value;
            if (selected) applyExisting(selected);
          }}
          style={{ padding: 10, borderRadius: 8, border: "1px solid #333", minWidth: 260 }}
        >
          <option value="">选择已有堆叠（可选）</option>
          {keys.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => void load()}
          style={{ padding: "10px 14px", borderRadius: 10, border: "1px solid #333", background: "transparent" }}
        >
          刷新列表
        </button>
      </div>

      <form onSubmit={save} style={{ display: "flex", gap: 12, flexDirection: "column", marginBottom: 16 }}>
        <input
          value={key}
          onChange={(e) => setKey(e.target.value)}
          placeholder="prompt_key，例如 reply / quote / original"
          style={{ padding: 10, borderRadius: 8, border: "1px solid #333", maxWidth: 520 }}
        />
        <textarea
          value={payloadText}
          onChange={(e) => setPayloadText(e.target.value)}
          rows={10}
          placeholder="payload JSON"
          style={{ padding: 10, borderRadius: 8, border: "1px solid #333", fontFamily: "monospace" }}
        />
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <button
            type="submit"
            style={{ padding: "10px 14px", borderRadius: 10, border: "none", background: "#2f6fed", color: "white" }}
          >
            保存
          </button>
          <input
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
            placeholder="seed（可选，用于复现）"
            style={{ padding: 10, borderRadius: 8, border: "1px solid #333", maxWidth: 220 }}
          />
          <button
            type="button"
            onClick={() => void doPreview()}
            style={{ padding: "10px 14px", borderRadius: 10, border: "1px solid #333", background: "transparent" }}
          >
            预览生成
          </button>
        </div>
      </form>

      {error ? <div style={{ color: "#ff6b6b", marginBottom: 12 }}>{error}</div> : null}
      {loading ? <div style={{ opacity: 0.8, marginBottom: 12 }}>加载中…</div> : null}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div style={{ border: "1px solid #222", borderRadius: 12, padding: 12 }}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>预览结果</div>
          <pre style={{ whiteSpace: "pre-wrap", margin: 0, fontFamily: "monospace", opacity: 0.9 }}>{preview || "(空)"}</pre>
        </div>
        <div style={{ border: "1px solid #222", borderRadius: 12, padding: 12 }}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>现有堆叠（只读）</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {stacks.map((s) => (
              <div key={s.id} style={{ border: "1px solid #333", borderRadius: 10, padding: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                  <div style={{ fontWeight: 700 }}>{s.key}</div>
                  <div style={{ opacity: 0.7 }}>v{s.version}</div>
                </div>
                <div style={{ opacity: 0.7, fontSize: 12, marginTop: 6 }}>
                  updated {new Date(s.updated_at).toLocaleString()}
                </div>
              </div>
            ))}
            {!stacks.length ? <div style={{ opacity: 0.7 }}>(暂无)</div> : null}
          </div>
        </div>
      </div>
    </div>
  );
}

