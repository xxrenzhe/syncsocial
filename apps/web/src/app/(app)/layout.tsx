"use client";

import { AppShell } from "@/components/AppShell";
import { useAuth } from "@/lib/auth";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const auth = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!auth.loading && !auth.user) {
      router.replace("/login");
    }
  }, [auth.loading, auth.user, router]);

  if (auth.loading) return <div style={{ padding: 24 }}>Loading…</div>;
  if (!auth.user) return null;

  return (
    <AppShell user={auth.user} activePath={pathname} onLogout={() => auth.logout()}>
      {children}
    </AppShell>
  );
}

