import Sidebar from "@/components/Sidebar";
import AuthGate from "@/components/AuthGate";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <div className="flex min-h-screen">
        <Sidebar />
        <main className="min-w-0 flex-1 pl-60">{children}</main>
      </div>
    </AuthGate>
  );
}
