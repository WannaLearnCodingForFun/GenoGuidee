"use client";

import Link from "next/link";
import { ShieldAlert } from "lucide-react";
import { useAccount } from "@/lib/useAccount";

export default function UnauthorizedPage() {
  const { account } = useAccount();
  return (
    <div className="mx-auto flex min-h-screen max-w-lg flex-col justify-center px-6">
      <ShieldAlert className="mb-4 size-8 text-warning" />
      <h1 className="text-2xl font-bold">You cannot open this page</h1>
      <p className="mt-2 text-sm text-muted">
        Your signed-in role{account?.role ? ` (${account.role})` : ""} does not include this
        workspace. Changing the URL does not grant access.
      </p>
      <Link href="/dashboard" className="mt-6 text-sm font-semibold text-cyan hover:underline">
        Return to your dashboard
      </Link>
    </div>
  );
}
