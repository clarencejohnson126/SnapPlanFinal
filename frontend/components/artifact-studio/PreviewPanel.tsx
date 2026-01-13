"use client";

import { useState } from "react";
import { Copy, Download, Code2, Check, Image, FileText, History, Link2 } from "lucide-react";
import { ArtifactRenderer } from "./ArtifactRenderer";
import { useLanguage } from "@/lib/i18n";
import type { Artifact } from "@/lib/artifact-api";

interface PreviewPanelProps {
  artifact: Artifact | null;
  isLoading: boolean;
  error: string | null;
  onOpenHistory: () => void;
}

export function PreviewPanel({
  artifact,
  isLoading,
  error,
  onOpenHistory,
}: PreviewPanelProps) {
  const { language } = useLanguage();
  const [showCode, setShowCode] = useState(false);
  const [copySuccess, setCopySuccess] = useState(false);
  const [urlCopySuccess, setUrlCopySuccess] = useState(false);

  const handleCopyJson = async () => {
    if (!artifact) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(artifact, null, 2));
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    } catch (err) {
      console.error("Copy failed:", err);
    }
  };

  const handleCopyCode = async () => {
    if (!artifact) return;
    try {
      await navigator.clipboard.writeText(artifact.code);
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    } catch (err) {
      console.error("Copy failed:", err);
    }
  };

  const handleCopyUrl = async () => {
    if (!artifact) return;
    try {
      const url = `${window.location.origin}/app/artifact-studio/view/${artifact.artifact_id}`;
      await navigator.clipboard.writeText(url);
      setUrlCopySuccess(true);
      setTimeout(() => setUrlCopySuccess(false), 2000);
    } catch (err) {
      console.error("Copy URL failed:", err);
    }
  };

  const handleDownloadSvg = () => {
    if (!artifact || artifact.type !== "svg") return;
    const blob = new Blob([artifact.code], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${artifact.title.replace(/\s+/g, "-").toLowerCase()}.svg`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleDownloadHtml = () => {
    if (!artifact) return;
    const html = `<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${artifact.title}</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px;
      background: #f9fafb;
    }
    .container {
      background: white;
      border-radius: 8px;
      padding: 24px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    h1 { margin-top: 0; color: #111827; }
    .summary { color: #4b5563; margin-bottom: 16px; }
    .bullets { color: #374151; padding-left: 20px; }
    .content { margin-top: 24px; }
    .meta { margin-top: 24px; font-size: 12px; color: #9ca3af; }
  </style>
</head>
<body>
  <div class="container">
    <h1>${artifact.title}</h1>
    <p class="summary">${artifact.summary}</p>
    <ul class="bullets">
      ${artifact.bullet_points.map((p) => `<li>${p}</li>`).join("\n      ")}
    </ul>
    <div class="content">
      ${artifact.type === "svg" ? artifact.code : `<div>${artifact.code}</div>`}
    </div>
    <p class="meta">Generated: ${new Date(artifact.created_at).toLocaleString("de-DE")}</p>
  </div>
</body>
</html>`;
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${artifact.title.replace(/\s+/g, "-").toLowerCase()}.html`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const getTypeLabel = (type: string) => {
    const labels: Record<string, string> = {
      svg: "SVG",
      mermaid: "Mermaid",
      html: "HTML",
    };
    return labels[type] || type.toUpperCase();
  };

  return (
    <div className="h-full flex flex-col bg-[#1A2942] rounded-xl border border-white/5 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-white truncate max-w-[200px]">
            {artifact?.title || (language === "de" ? "Vorschau" : "Preview")}
          </h2>
          {artifact && (
            <span className="px-2 py-0.5 bg-white/10 text-[#94A3B8] text-xs rounded">
              {getTypeLabel(artifact.type)}
            </span>
          )}
        </div>

        <div className="flex items-center gap-1">
          {/* History button */}
          <button
            onClick={onOpenHistory}
            className="p-2 rounded-lg bg-white/5 text-[#94A3B8] hover:text-white hover:bg-white/10 transition-colors"
            title={language === "de" ? "Verlauf" : "History"}
          >
            <History className="w-4 h-4" />
          </button>

          {artifact && (
            <>
              {/* Copy URL */}
              <button
                onClick={handleCopyUrl}
                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-[#00D4AA]/10 text-[#00D4AA] hover:bg-[#00D4AA]/20 transition-colors"
                title={language === "de" ? "URL kopieren" : "Copy URL"}
              >
                {urlCopySuccess ? (
                  <>
                    <Check className="w-4 h-4" />
                    <span className="text-xs font-medium">Copied!</span>
                  </>
                ) : (
                  <>
                    <Link2 className="w-4 h-4" />
                    <span className="text-xs font-medium">URL</span>
                  </>
                )}
              </button>

              {/* Code toggle */}
              <button
                onClick={() => setShowCode(!showCode)}
                className={`p-2 rounded-lg transition-colors ${
                  showCode
                    ? "bg-[#00D4AA]/20 text-[#00D4AA]"
                    : "bg-white/5 text-[#94A3B8] hover:text-white hover:bg-white/10"
                }`}
                title={showCode ? "Show preview" : "Show code"}
              >
                <Code2 className="w-4 h-4" />
              </button>

              {/* Copy JSON */}
              <button
                onClick={handleCopyJson}
                className="p-2 rounded-lg bg-white/5 text-[#94A3B8] hover:text-white hover:bg-white/10 transition-colors"
                title="Copy JSON"
              >
                {copySuccess ? (
                  <Check className="w-4 h-4 text-[#00D4AA]" />
                ) : (
                  <Copy className="w-4 h-4" />
                )}
              </button>

              {/* Download SVG (only for SVG type) */}
              {artifact.type === "svg" && (
                <button
                  onClick={handleDownloadSvg}
                  className="p-2 rounded-lg bg-white/5 text-[#94A3B8] hover:text-white hover:bg-white/10 transition-colors"
                  title="Download SVG"
                >
                  <Image className="w-4 h-4" />
                </button>
              )}

              {/* Download HTML */}
              <button
                onClick={handleDownloadHtml}
                className="p-2 rounded-lg bg-white/5 text-[#94A3B8] hover:text-white hover:bg-white/10 transition-colors"
                title="Download HTML"
              >
                <FileText className="w-4 h-4" />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Content Area */}
      <div className="flex-1 overflow-auto">
        {/* Loading State */}
        {isLoading && (
          <div className="h-full flex flex-col items-center justify-center p-8">
            <div className="relative">
              <div className="w-16 h-16 border-4 border-[#00D4AA]/20 rounded-full" />
              <div className="absolute inset-0 w-16 h-16 border-4 border-transparent border-t-[#00D4AA] rounded-full animate-spin" />
            </div>
            <p className="mt-6 text-[#94A3B8] text-center">
              {language === "de"
                ? "Generiere Skizze mit Claude AI..."
                : "Generating sketch with Claude AI..."}
            </p>
            <p className="mt-2 text-[#64748B] text-sm text-center">
              {language === "de"
                ? "Dies kann einige Sekunden dauern"
                : "This may take a few seconds"}
            </p>
          </div>
        )}

        {/* Error State */}
        {error && !isLoading && (
          <div className="p-4">
            <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg">
              <p className="text-red-400 font-medium mb-1">
                {language === "de" ? "Fehler bei der Generierung" : "Generation Error"}
              </p>
              <p className="text-red-400/80 text-sm">{error}</p>
            </div>
          </div>
        )}

        {/* Empty State */}
        {!isLoading && !error && !artifact && (
          <div className="h-full flex flex-col items-center justify-center text-center p-8">
            <div className="w-20 h-20 bg-white/5 rounded-2xl flex items-center justify-center mb-4">
              <svg
                className="w-10 h-10 text-[#64748B]"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                />
              </svg>
            </div>
            <p className="text-[#94A3B8] mb-2">
              {language === "de"
                ? "Keine Skizze generiert"
                : "No sketch generated"}
            </p>
            <p className="text-[#64748B] text-sm max-w-xs">
              {language === "de"
                ? "Geben Sie eine Beschreibung ein und klicken Sie auf 'Skizze generieren'"
                : "Enter a description and click 'Generate Sketch'"}
            </p>
          </div>
        )}

        {/* Artifact Display */}
        {artifact && !isLoading && (
          <div className="p-4 space-y-4">
            {/* Code View */}
            {showCode ? (
              <div className="relative">
                <button
                  onClick={handleCopyCode}
                  className="absolute top-2 right-2 p-1.5 rounded bg-white/10 text-[#94A3B8] hover:text-white hover:bg-white/20 transition-colors"
                  title="Copy code"
                >
                  <Copy className="w-3.5 h-3.5" />
                </button>
                <pre className="p-4 bg-[#0F1B2A] rounded-lg overflow-auto text-sm text-[#94A3B8] font-mono max-h-[400px]">
                  {artifact.code}
                </pre>
              </div>
            ) : (
              /* Preview */
              <div className="min-h-[300px] max-h-[500px] overflow-auto rounded-lg border border-white/5">
                <ArtifactRenderer
                  type={artifact.type}
                  code={artifact.code}
                  title={artifact.title}
                />
              </div>
            )}

            {/* Summary & Bullet Points */}
            <div className="p-4 bg-[#0F1B2A] rounded-lg space-y-3">
              <p className="text-sm text-white">{artifact.summary}</p>
              {artifact.bullet_points.length > 0 && (
                <ul className="space-y-1.5">
                  {artifact.bullet_points.map((point, i) => (
                    <li
                      key={i}
                      className="text-sm text-[#94A3B8] flex items-start gap-2"
                    >
                      <span className="text-[#00D4AA] mt-0.5">-</span>
                      {point}
                    </li>
                  ))}
                </ul>
              )}

              {/* Metadata */}
              <div className="pt-3 border-t border-white/5 flex flex-wrap gap-3 text-xs text-[#64748B]">
                {artifact.trade_preset && (
                  <span>
                    Gewerk: <span className="text-[#94A3B8]">{artifact.trade_preset}</span>
                  </span>
                )}
                {artifact.version_number > 1 && (
                  <span>
                    Version: <span className="text-[#94A3B8]">{artifact.version_number}</span>
                  </span>
                )}
                <span>
                  {new Date(artifact.created_at).toLocaleString(
                    language === "de" ? "de-DE" : "en-US",
                    { dateStyle: "short", timeStyle: "short" }
                  )}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
