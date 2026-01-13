"use client";

import { useEffect, useRef, useState, useMemo } from "react";
import dynamic from "next/dynamic";
import type { ArtifactType } from "@/lib/artifact-api";

// Dynamically import InteractiveArtifactViewer to avoid SSR issues with Web Audio API
const InteractiveArtifactViewer = dynamic(
  () => import("./InteractiveArtifactViewer"),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center h-full min-h-[400px] bg-stone-950">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-3 border-[#00D4AA]/20 border-t-[#00D4AA] rounded-full animate-spin" />
          <p className="text-stone-400 text-sm">Laden des interaktiven Viewers...</p>
        </div>
      </div>
    )
  }
);

interface ArtifactRendererProps {
  type: ArtifactType;
  code: string;
  title: string;
}

/**
 * Safely renders artifact content based on type.
 *
 * Security measures:
 * - Interactive: Uses pre-built viewer component with structured data
 * - SVG: Rendered directly (pre-sanitized on backend)
 * - Mermaid: Rendered via mermaid.js to SVG (safe)
 * - HTML: Rendered in sandboxed iframe (no scripts allowed)
 */
export function ArtifactRenderer({ type, code, title }: ArtifactRendererProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [mermaidSvg, setMermaidSvg] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Parse interactive data
  const interactiveData = useMemo(() => {
    if (type !== "interactive") return null;
    try {
      const data = JSON.parse(code);
      // Validate required fields
      if (!data.components || !data.svgContent) {
        throw new Error("Missing required interactive data fields");
      }
      // Add default categories if not present
      if (!data.layerCategories || data.layerCategories.length === 0) {
        data.layerCategories = [
          { id: "all", name: "Alle Komponenten", color: "#6B7280", description: "Vollständige Ansicht" },
          { id: "load-bearing", name: "Tragwerk", color: "#1E3A5F", description: "Lastabtragende Elemente" },
          { id: "finishing", name: "Bekleidung", color: "#8B7355", description: "Oberflächenschichten" },
          { id: "acoustic", name: "Akustik", color: "#4A6741", description: "Schallschutz" },
          { id: "fire-protection", name: "Brandschutz", color: "#8B2500", description: "Feuerwiderstand" },
          { id: "moisture", name: "Abdichtung", color: "#4A708B", description: "Feuchtigkeitsschutz" },
        ];
      }
      // Add default failure scenarios if not present
      if (!data.failureScenarios) {
        data.failureScenarios = [];
      }
      // Add default dimensions if not present
      if (!data.dimensions) {
        data.dimensions = { width: 500, height: 450 };
      }
      return data;
    } catch (err) {
      console.error("Failed to parse interactive data:", err);
      return null;
    }
  }, [type, code]);

  // Render Mermaid diagrams
  useEffect(() => {
    if (type !== "mermaid") return;

    const renderMermaid = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: "dark",
          themeVariables: {
            primaryColor: "#00D4AA",
            primaryTextColor: "#ffffff",
            primaryBorderColor: "#00D4AA",
            lineColor: "#94A3B8",
            secondaryColor: "#1A2942",
            tertiaryColor: "#0F1B2A",
            background: "#1A2942",
            mainBkg: "#1A2942",
            textColor: "#ffffff",
            nodeTextColor: "#ffffff",
          },
          flowchart: {
            htmlLabels: true,
            curve: "basis",
          },
        });

        // Generate unique ID for this render
        const id = `mermaid-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        const { svg } = await mermaid.render(id, code);
        setMermaidSvg(svg);
      } catch (err) {
        console.error("Mermaid render error:", err);
        setError(
          `Mermaid diagram error: ${err instanceof Error ? err.message : "Unknown error"}`
        );
      } finally {
        setIsLoading(false);
      }
    };

    renderMermaid();
  }, [type, code]);

  // Error display
  if (error) {
    return (
      <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg">
        <p className="text-red-400 text-sm font-medium mb-2">Render Error</p>
        <p className="text-red-400/80 text-sm">{error}</p>
        <details className="mt-3">
          <summary className="text-xs text-[#64748B] cursor-pointer hover:text-[#94A3B8]">
            Show raw code
          </summary>
          <pre className="mt-2 p-3 bg-[#0F1B2A] rounded text-xs text-[#94A3B8] overflow-auto max-h-48 font-mono">
            {code}
          </pre>
        </details>
      </div>
    );
  }

  // Interactive: Render with InteractiveArtifactViewer
  if (type === "interactive") {
    if (!interactiveData) {
      return (
        <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg">
          <p className="text-red-400 text-sm font-medium mb-2">Fehler beim Parsen der interaktiven Daten</p>
          <p className="text-red-400/80 text-sm">
            Die generierten Daten konnten nicht verarbeitet werden.
          </p>
          <details className="mt-3">
            <summary className="text-xs text-[#64748B] cursor-pointer hover:text-[#94A3B8]">
              Raw data anzeigen
            </summary>
            <pre className="mt-2 p-3 bg-[#0F1B2A] rounded text-xs text-[#94A3B8] overflow-auto max-h-48 font-mono">
              {code}
            </pre>
          </details>
        </div>
      );
    }

    return (
      <div className="w-full h-full min-h-[600px]">
        <InteractiveArtifactViewer data={interactiveData} title={title} />
      </div>
    );
  }

  // Loading state for Mermaid
  if (type === "mermaid" && isLoading) {
    return (
      <div className="flex items-center justify-center h-full min-h-[200px]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-3 border-[#00D4AA]/20 border-t-[#00D4AA] rounded-full animate-spin" />
          <p className="text-[#94A3B8] text-sm">Rendering diagram...</p>
        </div>
      </div>
    );
  }

  // SVG: Render directly in DOM (pre-sanitized on backend)
  if (type === "svg") {
    return (
      <div
        ref={containerRef}
        className="w-full h-full flex items-center justify-center bg-white rounded-lg p-4 overflow-auto"
        dangerouslySetInnerHTML={{ __html: code }}
      />
    );
  }

  // Mermaid: Render the generated SVG
  if (type === "mermaid") {
    if (!mermaidSvg) {
      return (
        <div className="flex items-center justify-center h-full min-h-[200px]">
          <p className="text-[#64748B]">No diagram generated</p>
        </div>
      );
    }
    return (
      <div
        ref={containerRef}
        className="w-full h-full flex items-center justify-center p-4 overflow-auto"
        dangerouslySetInnerHTML={{ __html: mermaidSvg }}
      />
    );
  }

  // HTML: Render in sandboxed iframe
  if (type === "html") {
    const sandboxedHtml = `
<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${title}</title>
  <style>
    * {
      box-sizing: border-box;
    }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      padding: 16px;
      margin: 0;
      background: #ffffff;
      color: #1a1a1a;
      line-height: 1.5;
    }
    table {
      border-collapse: collapse;
      width: 100%;
      margin: 16px 0;
    }
    th, td {
      border: 1px solid #e5e7eb;
      padding: 10px 12px;
      text-align: left;
    }
    th {
      background: #f9fafb;
      font-weight: 600;
    }
    tr:hover {
      background: #f9fafb;
    }
    h1, h2, h3, h4 {
      margin-top: 0;
      color: #111827;
    }
    ul, ol {
      margin: 8px 0;
      padding-left: 24px;
    }
    li {
      margin: 4px 0;
    }
    .note {
      background: #fef3c7;
      border-left: 4px solid #f59e0b;
      padding: 12px;
      margin: 16px 0;
    }
    .warning {
      background: #fee2e2;
      border-left: 4px solid #ef4444;
      padding: 12px;
      margin: 16px 0;
    }
  </style>
</head>
<body>
${code}
</body>
</html>`;

    return (
      <iframe
        title={title}
        srcDoc={sandboxedHtml}
        sandbox="allow-same-origin"
        className="w-full h-full min-h-[300px] border-0 rounded-lg bg-white"
        style={{ colorScheme: "light" }}
      />
    );
  }

  // Fallback for unknown type
  return (
    <div className="p-4 bg-amber-500/10 border border-amber-500/20 rounded-lg">
      <p className="text-amber-400 text-sm">
        Unsupported artifact type: {type}
      </p>
    </div>
  );
}
