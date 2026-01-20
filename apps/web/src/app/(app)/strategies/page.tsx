"use client";

import { useAuth } from "@/lib/auth";
import type { PlatformPublic, StrategyPublic } from "@/lib/types";
import { useEffect, useMemo, useState } from "react";

export default function StrategiesPage() {
  const auth = useAuth();
  const [strategies, setStrategies] = useState<StrategyPublic[]>([]);
  const [platforms, setPlatforms] = useState<PlatformPublic[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const platformOptions = useMemo(
    () =>
      platforms.length
        ? platforms.map((p) => ({ value: p.platform_key, label: p.display_name }))
        : [
            { value: "x", label: "X（Twitter）" },
            { value: "reddit", label: "Reddit" },
          ],
    [platforms]
  );

  const platformByKey = useMemo(() => {
    const map: Record<string, PlatformPublic> = {};
    for (const p of platforms) map[p.platform_key] = p;
    return map;
  }, [platforms]);

  const [name, setName] = useState("");
  const [platformKey, setPlatformKey] = useState("x");
  const [templateKey, setTemplateKey] = useState("");
  const [configText, setConfigText] = useState("{}");

  const templates = useMemo(
    () => [
      {
        key: "x_like_targets",
        label: "X：点赞（指定链接）",
        platform_key: "x",
        config: { type: "x_like", targets: ["https://x.com/username/status/1234567890123456789"], max_actions: 1, bandwidth_mode: "eco" },
      },
      {
        key: "x_repost_targets",
        label: "X：转发（指定链接）",
        platform_key: "x",
        config: { type: "x_repost", targets: ["https://x.com/username/status/1234567890123456789"], max_actions: 1, bandwidth_mode: "eco" },
      },
      {
        key: "x_reply_targets",
        label: "X：评论/回复（指定链接）",
        platform_key: "x",
        config: {
          type: "x_reply",
          targets: ["https://x.com/username/status/1234567890123456789"],
          reply_texts: ["很赞", "学习了", "感谢分享"],
          repeat_window_days: 7,
          max_actions: 1,
          bandwidth_mode: "eco",
        },
      },
      {
        key: "x_quote_targets",
        label: "X：引用转发（指定链接）",
        platform_key: "x",
        config: {
          type: "x_quote",
          targets: ["https://x.com/username/status/1234567890123456789"],
          quote_texts: ["收藏一下", "值得转发", "mark"],
          repeat_window_days: 7,
          max_actions: 1,
          bandwidth_mode: "eco",
        },
      },
      {
        key: "x_publish_post",
        label: "X：发布推文（文本/可选图片URL）",
        platform_key: "x",
        config: {
          type: "x_publish_post",
          text: "hello world",
          media_urls: [],
          max_actions: 1,
          repeat_window_days: 1,
          max_media_bytes: 153600,
          max_download_bytes: 5242880,
          compose_url: "https://x.com/compose/post",
          bandwidth_mode: "balanced",
        },
      },
      {
        key: "reddit_upvote_targets",
        label: "Reddit：Upvote（指定链接）",
        platform_key: "reddit",
        config: { type: "reddit_upvote", targets: ["https://www.reddit.com/r/test/comments/abcdef/title/"], max_actions: 1, bandwidth_mode: "eco" },
      },
      {
        key: "reddit_comment_targets",
        label: "Reddit：评论（指定链接）",
        platform_key: "reddit",
        config: {
          type: "reddit_comment",
          targets: ["https://www.reddit.com/r/test/comments/abcdef/title/"],
          texts: ["感谢分享", "学习了", "很有启发"],
          repeat_window_days: 7,
          max_actions: 1,
          bandwidth_mode: "eco",
        },
      },
      {
        key: "reddit_post",
        label: "Reddit：发帖（subreddit）",
        platform_key: "reddit",
        config: { type: "reddit_post", subreddit: "test", title: "Hello", text: "First post", repeat_window_days: 7, max_actions: 1, bandwidth_mode: "eco" },
      },
      {
        key: "x_search_like",
        label: "X：关键词搜索→点赞",
        platform_key: "x",
        config: {
          type: "x_search_like",
          query: "ai tools",
          search_mode: "live",
          max_candidates: 20,
          scroll_limit: 6,
          max_actions: 3,
          bandwidth_mode: "eco",
        },
      },
      {
        key: "x_search_repost",
        label: "X：关键词搜索→转发",
        platform_key: "x",
        config: {
          type: "x_search_repost",
          query: "ai tools",
          search_mode: "live",
          max_candidates: 20,
          scroll_limit: 6,
          max_actions: 3,
          bandwidth_mode: "eco",
        },
      },
      {
        key: "x_search_reply",
        label: "X：关键词搜索→评论/回复",
        platform_key: "x",
        config: {
          type: "x_search_reply",
          query: "ai tools",
          search_mode: "live",
          max_candidates: 20,
          scroll_limit: 6,
          max_actions: 2,
          reply_texts: ["很赞", "学习了", "感谢分享"],
          repeat_window_days: 7,
          bandwidth_mode: "eco",
        },
      },
      {
        key: "x_search_quote",
        label: "X：关键词搜索→引用转发",
        platform_key: "x",
        config: {
          type: "x_search_quote",
          query: "ai tools",
          search_mode: "live",
          max_candidates: 20,
          scroll_limit: 6,
          max_actions: 2,
          quote_texts: ["收藏一下", "值得转发", "mark"],
          repeat_window_days: 7,
          bandwidth_mode: "eco",
        },
      },
      {
        key: "keyword_repost",
        label: "X：关键词改写发布（keyword_repost，PromptStack + LLM 可选）",
        platform_key: "x",
        config: {
          type: "keyword_repost",
          query: "ai tools",
          search_mode: "live",
          max_candidates: 20,
          scroll_limit: 6,
          max_actions: 1,
          repeat_window_days: 7,
          keyword_repost_prompt_stack_key: "keyword_repost",
          use_llm: true,
          bandwidth_mode: "balanced",
        },
      },
      {
        key: "x_verified_like",
        label: "X：蓝V搜索→点赞（DOM兜底）",
        platform_key: "x",
        config: {
          type: "x_verified_like",
          query: "ai tools",
          search_mode: "live",
          max_candidates: 20,
          scroll_limit: 8,
          max_actions: 3,
          bandwidth_mode: "eco",
        },
      },
      {
        key: "x_verified_repost",
        label: "X：蓝V搜索→转发（DOM兜底）",
        platform_key: "x",
        config: {
          type: "x_verified_repost",
          query: "ai tools",
          search_mode: "live",
          max_candidates: 20,
          scroll_limit: 8,
          max_actions: 3,
          bandwidth_mode: "eco",
        },
      },
      {
        key: "x_verified_reply",
        label: "X：蓝V搜索→评论/回复（DOM兜底）",
        platform_key: "x",
        config: {
          type: "x_verified_reply",
          query: "ai tools",
          search_mode: "live",
          max_candidates: 20,
          scroll_limit: 8,
          max_actions: 2,
          reply_texts: ["很赞", "学习了", "感谢分享"],
          repeat_window_days: 7,
          bandwidth_mode: "eco",
        },
      },
      {
        key: "x_verified_quote",
        label: "X：蓝V搜索→引用转发（DOM兜底）",
        platform_key: "x",
        config: {
          type: "x_verified_quote",
          query: "ai tools",
          search_mode: "live",
          max_candidates: 20,
          scroll_limit: 8,
          max_actions: 2,
          quote_texts: ["收藏一下", "值得转发", "mark"],
          repeat_window_days: 7,
          bandwidth_mode: "eco",
        },
      },
    ],
    []
  );

  function requiredCapabilitiesForType(type: string): string[] {
    const t = type.trim().toLowerCase();
    const caps: string[] = [];
    if (t.startsWith("x_search_") || t.startsWith("x_verified_") || t === "keyword_repost" || t === "x_keyword_repost") {
      caps.push("SOURCE_KEYWORD_SEARCH");
    }
    if (t.startsWith("x_verified_")) caps.push("TARGET_VERIFIED_ONLY");
    if (t.includes("publish_post") || t === "reddit_post") caps.push("PUBLISH_POST");
    if (t.includes("like") || t.includes("upvote")) caps.push("ENGAGE_LIKE");
    if (t.includes("reply") || t.includes("comment")) caps.push("ENGAGE_COMMENT");
    if (t.includes("repost") || t.includes("retweet")) caps.push("ENGAGE_REPOST");
    if (t.includes("quote")) caps.push("ENGAGE_QUOTE");
    return Array.from(new Set(caps));
  }

  function applyTemplate(key: string) {
    const t = templates.find((it) => it.key === key);
    if (!t) return;
    setPlatformKey(t.platform_key);
    setConfigText(JSON.stringify(t.config, null, 2));
  }

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [strategiesRes, platformsRes] = await Promise.all([auth.apiFetch("/strategies"), auth.apiFetch("/platforms")]);
      if (!strategiesRes.ok) throw new Error(await strategiesRes.text());
      const data = (await strategiesRes.json()) as StrategyPublic[];
      setStrategies(data);

      if (platformsRes.ok) {
        const platformsData = (await platformsRes.json()) as PlatformPublic[];
        setPlatforms(platformsData);
        if (platformsData.length && !platformsData.some((p) => p.platform_key === platformKey)) {
          setPlatformKey(platformsData[0].platform_key);
        }
      }
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
        {platformByKey[platformKey]?.capabilities?.length ? (
          <div style={{ alignSelf: "center", opacity: 0.75, fontSize: 12 }}>
            capabilities：{platformByKey[platformKey].capabilities.join(", ")}
          </div>
        ) : null}
        <select
          value={templateKey}
          onChange={(e) => {
            const key = e.target.value;
            setTemplateKey(key);
            if (key) applyTemplate(key);
          }}
          style={{ padding: 10, borderRadius: 8, border: "1px solid #333" }}
        >
          <option value="">选择模板（可选）</option>
          {templates
            .filter((t) => {
              if (!platforms.length) return true;
              const platform = platformByKey[t.platform_key];
              if (!platform) return false;
              const required = requiredCapabilitiesForType(String((t.config as Record<string, unknown>).type || ""));
              return required.every((cap) => platform.capabilities.includes(cap));
            })
            .map((t) => (
              <option key={t.key} value={t.key}>
                {t.label}
              </option>
            ))}
        </select>
        <textarea
          value={configText}
          onChange={(e) => setConfigText(e.target.value)}
          placeholder='config JSON，比如 {"key":"value"}'
          rows={6}
          style={{ padding: 10, borderRadius: 8, border: "1px solid #333", minWidth: 520, fontFamily: "monospace" }}
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
