"use client";

import { RiGithubLine, RiErrorWarningLine } from "@remixicon/react";
import { type ChangeEvent } from "react";
import { cx } from "@/utils/cx";

const GITHUB_RE = /^https:\/\/github\.com\/[^/]+\/[^/]+(\/.*)?$/;

interface ScannerGithubInputProps {
  value: string;
  onChange: (value: string) => void;
}

export function ScannerGithubInput({ value, onChange }: ScannerGithubInputProps) {
  const invalid = value.length > 0 && !GITHUB_RE.test(value);

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor="github-url" className="text-body-medium text-text-primary">
        GitHub Repository URL
      </label>
      <div
        className={cx(
          "flex items-center gap-2 rounded-xl border bg-background-primary-default px-3 py-2 transition-colors",
          invalid
            ? "border-border-error-default"
            : "border-border-button-default focus-within:border-accent-500",
        )}
      >
        <RiGithubLine
          className={cx("size-5 shrink-0", invalid ? "text-text-error-primary" : "text-foreground-icon-secondary")}
          aria-hidden
        />
        <input
          id="github-url"
          type="url"
          value={value}
          onChange={(event: ChangeEvent<HTMLInputElement>) => onChange(event.target.value)}
          placeholder="https://github.com/owner/repo"
          autoComplete="off"
          spellCheck={false}
          aria-invalid={invalid}
          aria-describedby={invalid ? "github-url-error" : undefined}
          className="min-w-0 flex-1 bg-transparent text-body-regular text-text-primary caret-text-primary outline-none placeholder:text-text-placeholder"
        />
      </div>
      {invalid && (
        <p id="github-url-error" className="flex items-center gap-1 text-body-2-regular text-text-error-primary">
          <RiErrorWarningLine className="size-4 shrink-0" aria-hidden />
          Please enter a valid GitHub repository URL (e.g. https://github.com/owner/repo).
        </p>
      )}
    </div>
  );
}
