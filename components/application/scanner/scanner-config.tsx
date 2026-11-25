"use client";

import { Switch } from "@/components/base/switch/switch";
import { Select, SelectItem } from "@/components/base/select/select";
import { cx } from "@/utils/cx";

export interface ScanConfig {
  security: boolean;
  dependencies: boolean;
  architecture: boolean;
  comparison: boolean;
  baseline: string;
}

interface ScannerConfigProps {
  config: ScanConfig;
  onChange: (config: ScanConfig) => void;
}

const BASELINES = [
  { id: "clean", label: "Clean Architecture" },
  { id: "hexagonal", label: "Hexagonal Architecture" },
  { id: "mvc", label: "MVC" },
  { id: "layered", label: "Layered (N-Tier)" },
  { id: "custom", label: "Custom Baseline" },
];

export function ScannerConfig({ config, onChange }: ScannerConfigProps) {
  const set = <K extends keyof ScanConfig>(key: K, value: ScanConfig[K]) =>
    onChange({ ...config, [key]: value });

  return (
    <div className="flex flex-col gap-4 rounded-3xl border border-border-button-default bg-background-secondary-default p-5">
      <h3 className="text-headline-medium text-text-primary">Scan Options</h3>

      <div className="flex flex-col gap-0 divide-y divide-separator-border">
        <ConfigRow
          label="Security Vulnerabilities"
          description="OWASP Top 10, injection flaws, hardcoded secrets, XSS, CSRF"
        >
          <Switch
            aria-label="Security Vulnerabilities"
            isSelected={config.security}
            onChange={(v) => set("security", v)}
          />
        </ConfigRow>

        <ConfigRow
          label="Dependency Audit"
          description="Outdated packages, known CVEs, license conflicts"
        >
          <Switch
            aria-label="Dependency Audit"
            isSelected={config.dependencies}
            onChange={(v) => set("dependencies", v)}
          />
        </ConfigRow>

        <ConfigRow
          label="Architecture Analysis"
          description="Cyclomatic complexity, coupling, boundary violations, circular deps"
        >
          <Switch
            aria-label="Architecture Analysis"
            isSelected={config.architecture}
            onChange={(v) => set("architecture", v)}
          />
        </ConfigRow>

        <ConfigRow
          label="Architecture Comparison"
          description="Compare against a reference architecture pattern"
        >
          <Switch
            aria-label="Architecture Comparison"
            isSelected={config.comparison}
            onChange={(v) => set("comparison", v)}
          />
        </ConfigRow>
      </div>

      {config.comparison && (
        <div className="flex flex-col gap-1.5 pt-1">
          <label className="text-body-medium text-text-primary">Compare against</label>
          <Select
            aria-label="Reference architecture"
            selectedKey={config.baseline}
            onSelectionChange={(key) => set("baseline", String(key))}
            triggerClassName="w-full"
          >
            {BASELINES.map(({ id, label }) => (
              <SelectItem key={id} id={id}>{label}</SelectItem>
            ))}
          </Select>
        </div>
      )}
    </div>
  );
}

function ConfigRow({
  label,
  description,
  children,
}: {
  label: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cx("flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0")}>
      <div className="flex flex-col gap-0.5">
        <span className="text-body-medium text-text-primary">{label}</span>
        <span className="text-body-2-regular text-text-secondary">{description}</span>
      </div>
      {children}
    </div>
  );
}
