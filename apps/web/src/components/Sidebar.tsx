"use client";

import type { UserPublic } from "@/lib/types";
import Link from "next/link";

type NavItem = { href: string; label: string };

const userNav: NavItem[] = [{ href: "/", label: "仪表盘" }];
const adminNav: NavItem[] = [{ href: "/admin/users", label: "用户管理" }];

function NavList({ items, activePath }: { items: NavItem[]; activePath: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {items.map((it) => {
        const active = activePath === it.href;
        return (
          <Link
            key={it.href}
            href={it.href}
            style={{
              padding: "10px 12px",
              borderRadius: 10,
              border: active ? "1px solid #2f6fed" : "1px solid transparent",
              background: active ? "rgba(47, 111, 237, 0.15)" : "transparent",
            }}
          >
            {it.label}
          </Link>
        );
      })}
    </div>
  );
}

export function Sidebar({
  user,
  activePath,
  onLogout,
}: {
  user: UserPublic;
  activePath: string;
  onLogout: () => void;
}) {
  return (
    <aside style={{ width: 260, padding: 16, display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        <div style={{ fontWeight: 700, fontSize: 18 }}>SyncSocial</div>
        <div style={{ opacity: 0.7, fontSize: 13 }}>SaaS Console</div>
      </div>

      <div>
        <div style={{ opacity: 0.7, fontSize: 12, marginBottom: 8 }}>用户功能</div>
        <NavList items={userNav} activePath={activePath} />
      </div>

      {user.role === "admin" ? (
        <div>
          <div style={{ opacity: 0.7, fontSize: 12, marginBottom: 8 }}>管理员管理</div>
          <NavList items={adminNav} activePath={activePath} />
        </div>
      ) : null}

      <div style={{ marginTop: "auto" }}>
        <button
          type="button"
          onClick={onLogout}
          style={{
            width: "100%",
            padding: "10px 12px",
            borderRadius: 10,
            border: "1px solid #333",
            background: "transparent",
          }}
        >
          退出登录
        </button>
      </div>
    </aside>
  );
}

