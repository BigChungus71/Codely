import { RiShieldCheckLine } from "@remixicon/react";
import { AppShell } from "@/components/application/app-shell/app-shell";
import { ScannerPanel } from "@/components/application/scanner/scanner-panel";

export const metadata = {
  title: "Scanner — Codely",
  description: "Scan files and GitHub repositories for vulnerabilities, security issues, and architectural flaws.",
};

export default function ScannerPage() {
  return (
    <AppShell title="Scanner" icon={RiShieldCheckLine} actions={null}>
      <ScannerPanel />
    </AppShell>
  );
}
