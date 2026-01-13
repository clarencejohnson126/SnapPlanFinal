"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowLeft, Download, Copy, Check, ExternalLink } from "lucide-react";
import Link from "next/link";
import { getArtifact, type Artifact } from "@/lib/artifact-api";
import { ArtifactRenderer } from "@/components/artifact-studio/ArtifactRenderer";

export default function ArtifactViewPage() {
  const params = useParams();
  const id = params.id as string;

  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copySuccess, setCopySuccess] = useState(false);

  useEffect(() => {
    async function loadArtifact() {
      try {
        const data = await getArtifact(id);
        setArtifact(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Artifact not found");
      } finally {
        setLoading(false);
      }
    }

    if (id) {
      loadArtifact();
    }
  }, [id]);

  const handleCopyUrl = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    } catch (err) {
      console.error("Copy failed:", err);
    }
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
    * { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      margin: 0;
      padding: 24px;
      background: #0F172A;
      color: #E2E8F0;
      min-height: 100vh;
    }
    .container {
      max-width: 1200px;
      margin: 0 auto;
    }
    h1 {
      color: #F8FAFC;
      margin: 0 0 8px 0;
      font-size: 24px;
    }
    .summary {
      color: #94A3B8;
      margin-bottom: 24px;
      font-size: 14px;
    }
    .content {
      background: #1E293B;
      border-radius: 12px;
      padding: 24px;
      margin-bottom: 24px;
    }
    .content svg {
      max-width: 100%;
      height: auto;
    }
    .bullets {
      background: #1E293B;
      border-radius: 12px;
      padding: 20px;
      list-style: none;
      margin: 0;
    }
    .bullets li {
      color: #94A3B8;
      padding: 8px 0;
      border-bottom: 1px solid #334155;
      font-size: 14px;
    }
    .bullets li:last-child {
      border-bottom: none;
    }
    .bullets li::before {
      content: "- ";
      color: #00D4AA;
    }
    .meta {
      margin-top: 24px;
      font-size: 12px;
      color: #64748B;
      text-align: center;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>${artifact.title}</h1>
    <p class="summary">${artifact.summary}</p>
    <div class="content">
      ${artifact.code}
    </div>
    <ul class="bullets">
      ${artifact.bullet_points.map((p) => `<li>${p}</li>`).join("\n      ")}
    </ul>
    <p class="meta">Generated with SnapPlan Artifact Studio - ${new Date(artifact.created_at).toLocaleString("de-DE")}</p>
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

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0F172A] flex items-center justify-center">
        <div className="text-center">
          <div className="relative inline-block">
            <div className="w-16 h-16 border-4 border-[#00D4AA]/20 rounded-full" />
            <div className="absolute inset-0 w-16 h-16 border-4 border-transparent border-t-[#00D4AA] rounded-full animate-spin" />
          </div>
          <p className="mt-6 text-[#94A3B8]">Loading artifact...</p>
        </div>
      </div>
    );
  }

  if (error || !artifact) {
    return (
      <div className="min-h-screen bg-[#0F172A] flex items-center justify-center">
        <div className="text-center">
          <div className="w-20 h-20 bg-red-500/10 rounded-2xl flex items-center justify-center mb-4 mx-auto">
            <svg className="w-10 h-10 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h1 className="text-xl font-semibold text-white mb-2">Artifact Not Found</h1>
          <p className="text-[#94A3B8] mb-6">{error || "The requested artifact could not be found."}</p>
          <Link
            href="/app/artifact-studio"
            className="inline-flex items-center gap-2 px-4 py-2 bg-[#00D4AA] text-[#0F172A] rounded-lg font-medium hover:bg-[#00D4AA]/90 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Studio
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0F172A]">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-[#0F172A]/95 backdrop-blur border-b border-white/5">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link
              href="/app/artifact-studio"
              className="p-2 rounded-lg bg-white/5 text-[#94A3B8] hover:text-white hover:bg-white/10 transition-colors"
            >
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div>
              <h1 className="text-lg font-semibold text-white">{artifact.title}</h1>
              <p className="text-sm text-[#64748B]">
                {artifact.trade_preset && <span className="capitalize">{artifact.trade_preset}</span>}
                {artifact.trade_preset && " - "}
                {new Date(artifact.created_at).toLocaleString("de-DE")}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleCopyUrl}
              className="inline-flex items-center gap-2 px-3 py-2 bg-white/5 text-[#94A3B8] rounded-lg hover:text-white hover:bg-white/10 transition-colors"
            >
              {copySuccess ? (
                <>
                  <Check className="w-4 h-4 text-[#00D4AA]" />
                  <span className="text-sm">Copied!</span>
                </>
              ) : (
                <>
                  <Copy className="w-4 h-4" />
                  <span className="text-sm">Copy URL</span>
                </>
              )}
            </button>
            <button
              onClick={handleDownloadHtml}
              className="inline-flex items-center gap-2 px-3 py-2 bg-[#00D4AA] text-[#0F172A] rounded-lg font-medium hover:bg-[#00D4AA]/90 transition-colors"
            >
              <Download className="w-4 h-4" />
              <span className="text-sm">Download</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 py-8">
        {/* Summary */}
        <div className="mb-6">
          <p className="text-[#94A3B8]">{artifact.summary}</p>
        </div>

        {/* Artifact Preview */}
        <div className="bg-[#1A2942] rounded-xl border border-white/5 overflow-hidden mb-6">
          <div className="p-6">
            <ArtifactRenderer
              type={artifact.type}
              code={artifact.code}
              title={artifact.title}
            />
          </div>
        </div>

        {/* Bullet Points */}
        {artifact.bullet_points.length > 0 && (
          <div className="bg-[#1A2942] rounded-xl border border-white/5 p-6">
            <h2 className="text-white font-medium mb-4">Key Points</h2>
            <ul className="space-y-2">
              {artifact.bullet_points.map((point, i) => (
                <li key={i} className="flex items-start gap-2 text-[#94A3B8]">
                  <span className="text-[#00D4AA]">-</span>
                  {point}
                </li>
              ))}
            </ul>
          </div>
        )}
      </main>
    </div>
  );
}
