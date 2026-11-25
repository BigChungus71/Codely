"use client";

import { RiShieldCheckLine } from "@remixicon/react";
import { AppShell } from "@/components/application/app-shell/app-shell";
import { RepositoryScanner } from "@/components/application/scanner/repository-scanner";
import { ScannerPanel } from "@/components/application/scanner/scanner-panel";

export default function ScannerPage() {
  return (
    <AppShell title="Scanner" icon={RiShieldCheckLine} actions={null}>
      <RepositoryScanner />
      <details className="mt-6">
        <summary className="cursor-pointer text-body-medium text-text-secondary">Review uploaded snippets with AI</summary>
        <ScannerPanel />
      </details>
    </AppShell>
  );
}
