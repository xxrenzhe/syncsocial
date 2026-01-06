"use client";

import type { UserPublic } from "@/lib/types";
import Link from "next/link";
import { Sidebar } from "./Sidebar";

export function AppShell({
  children,
  user,
  activePath,
  onLogout,
}: {
  children: React.ReactNode;
  user: UserPublic;
  activePath: string;
  onLogout: () => void;
}) {
  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      <Sidebar user={user} activePath={activePath} onLogout={onLogout} />
      <main style={{ flex: 1, borderLeft: "1px solid #222" }}>
        <div style={{ padding: "12px 16px", borderBottom: "1px solid #222", display: "flex", gap: 12 }}>
          <Link href="/" style={{ fontWeight: 600 }}>
            SyncSocial Console
          </Link>
          <div style={{ marginLeft: "auto", opacity: 0.8 }}>{user.email}</div>
        </div>
        {children}
      </main>
    </div>
  );
}

