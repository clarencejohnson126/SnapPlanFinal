"use client";

import { useState, useCallback } from "react";
import { PromptPanel } from "@/components/artifact-studio/PromptPanel";
import { PreviewPanel } from "@/components/artifact-studio/PreviewPanel";
import { HistoryDrawer } from "@/components/artifact-studio/HistoryDrawer";
import {
  generateArtifact,
  type Artifact,
  type ArtifactContext,
} from "@/lib/artifact-api";
import { useLanguage } from "@/lib/i18n";

export default function ArtifactStudioPage() {
  const { language } = useLanguage();
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);

  const handleGenerate = useCallback(
    async (prompt: string, trade?: string, context?: ArtifactContext) => {
      setIsGenerating(true);
      setError(null);

      try {
        const response = await generateArtifact({
          prompt,
          trade_preset: trade,
          context,
        });

        if (response.success && response.artifact) {
          setArtifact(response.artifact);
        } else {
          setError(
            response.error ||
              (language === "de"
                ? "Generierung fehlgeschlagen"
                : "Generation failed")
          );
        }
      } catch (err) {
        console.error("Generation error:", err);
        setError(
          err instanceof Error
            ? err.message
            : language === "de"
            ? "Ein unbekannter Fehler ist aufgetreten"
            : "An unknown error occurred"
        );
      } finally {
        setIsGenerating(false);
      }
    },
    [language]
  );

  const handleSelectArtifact = useCallback((selectedArtifact: Artifact) => {
    setArtifact(selectedArtifact);
    setError(null);
  }, []);

  return (
    <div className="h-[calc(100vh-8rem)] flex flex-col">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">
          {language === "de" ? "Artifact Studio" : "Artifact Studio"}
        </h1>
        <p className="text-[#94A3B8] mt-1">
          {language === "de"
            ? "Generieren Sie interaktive Baudetail-Skizzen mit KI"
            : "Generate interactive construction detail sketches with AI"}
        </p>
      </div>

      {/* Main Content - Two Column Layout */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-2 gap-6 min-h-0">
        {/* Left Panel: Prompt Input */}
        <PromptPanel onGenerate={handleGenerate} isGenerating={isGenerating} />

        {/* Right Panel: Preview */}
        <PreviewPanel
          artifact={artifact}
          isLoading={isGenerating}
          error={error}
          onOpenHistory={() => setIsHistoryOpen(true)}
        />
      </div>

      {/* History Drawer */}
      <HistoryDrawer
        isOpen={isHistoryOpen}
        onClose={() => setIsHistoryOpen(false)}
        onSelectArtifact={handleSelectArtifact}
        currentArtifactId={artifact?.artifact_id}
      />
    </div>
  );
}
