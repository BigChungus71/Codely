"use client";

import { RiUploadCloud2Line, RiCloseLine, RiFileCodeLine } from "@remixicon/react";
import { useRef, useState, type DragEvent, type ChangeEvent } from "react";
import { cx } from "@/utils/cx";

const ACCEPTED = [".zip", ".tar.gz", ".json", ".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".java", ".md", ".yaml", ".yml", ".toml"];
const ACCEPT_ATTR = ACCEPTED.join(",");

export interface ScanFile {
  file: File;
  id: string;
}

interface ScannerUploadProps {
  files: ScanFile[];
  onChange: (files: ScanFile[]) => void;
}

export function ScannerUpload({ files, onChange }: ScannerUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const addFiles = (incoming: FileList | null) => {
    if (!incoming) return;
    const next: ScanFile[] = Array.from(incoming).map((file) => ({
      file,
      id: `${file.name}-${file.size}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    }));
    onChange([...files, ...next]);
  };

  const removeFile = (id: string) => onChange(files.filter((f) => f.id !== id));

  const onDragOver = (event: DragEvent) => {
    event.preventDefault();
    setDragging(true);
  };

  const onDragLeave = () => setDragging(false);

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    addFiles(event.dataTransfer.files);
  };

  const onInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    addFiles(event.target.files);
    // Reset so the same file can be re-added after removal.
    event.target.value = "";
  };

  return (
    <div className="flex flex-col gap-3">
      {/* Drop zone */}
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        aria-label="Upload files for scanning"
        className={cx(
          "flex w-full cursor-pointer flex-col items-center justify-center gap-3 rounded-3xl border-2 border-dashed px-6 py-10 transition-colors",
          dragging
            ? "border-accent-500 bg-pill-tab-blue-selected-background"
            : "border-border-button-default bg-background-secondary-default hover:bg-background-secondary-hover",
        )}
      >
        <RiUploadCloud2Line
          className={cx("size-10 transition-colors", dragging ? "text-accent-500" : "text-foreground-icon-secondary")}
          aria-hidden
        />
        <div className="flex flex-col gap-1 text-center">
          <p className="text-headline-medium text-text-primary">Drop files here or click to upload</p>
          <p className="text-body-regular text-text-secondary">
            Supports {ACCEPTED.join(", ")}
          </p>
        </div>
      </button>

      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPT_ATTR}
        onChange={onInputChange}
        className="sr-only"
        aria-hidden
      />

      {/* File list */}
      {files.length > 0 && (
        <ul className="flex flex-col gap-2" aria-label="Files queued for scanning">
          {files.map(({ file, id }) => (
            <li
              key={id}
              className="flex items-center gap-3 rounded-xl border border-border-button-default bg-background-primary-default px-3 py-2"
            >
              <RiFileCodeLine className="size-4 shrink-0 text-foreground-icon-secondary" aria-hidden />
              <span className="min-w-0 flex-1 truncate text-body-medium text-text-primary">{file.name}</span>
              <span className="shrink-0 text-body-2-regular text-text-tertiary">
                {formatBytes(file.size)}
              </span>
              <button
                type="button"
                onClick={() => removeFile(id)}
                aria-label={`Remove ${file.name}`}
                className="inline-flex size-5 shrink-0 cursor-pointer items-center justify-center rounded-md text-foreground-icon-secondary hover:text-foreground-icon-primary"
              >
                <RiCloseLine className="size-4" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
