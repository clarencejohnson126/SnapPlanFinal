"use client";

import { useEffect, useState } from "react";
import { X, Loader2, Trash2, ChevronRight, FileImage, FileText, GitBranch } from "lucide-react";
import { useLanguage } from "@/lib/i18n";
import { listArtifacts, deleteArtifact, type Artifact } from "@/lib/artifact-api";

interface HistoryDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectArtifact: (artifact: Artifact) => void;
  currentArtifactId?: string;
}

export function HistoryDrawer({
  isOpen,
  onClose,
  onSelectArtifact,
  currentArtifactId,
}: HistoryDrawerProps) {
  const { language } = useLanguage();
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Load artifacts when drawer opens
  useEffect(() => {
    if (!isOpen) return;

    const loadArtifacts = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const response = await listArtifacts(50, 0);
        setArtifacts(response.artifacts);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load history"
        );
      } finally {
        setIsLoading(false);
      }
    };

    loadArtifacts();
  }, [isOpen]);

  const handleDelete = async (artifactId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (deletingId) return;

    const confirmed = window.confirm(
      language === "de"
        ? "Möchten Sie dieses Artefakt wirklich löschen?"
        : "Are you sure you want to delete this artifact?"
    );
    if (!confirmed) return;

    setDeletingId(artifactId);
    try {
      await deleteArtifact(artifactId);
      setArtifacts((prev) => prev.filter((a) => a.artifact_id !== artifactId));
    } catch (err) {
      console.error("Delete failed:", err);
    } finally {
      setDeletingId(null);
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case "svg":
        return <FileImage className="w-4 h-4" />;
      case "mermaid":
        return <GitBranch className="w-4 h-4" />;
      default:
        return <FileText className="w-4 h-4" />;
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffHours < 1) {
      return language === "de" ? "Gerade eben" : "Just now";
    }
    if (diffHours < 24) {
      return language === "de"
        ? `Vor ${diffHours} Stunde${diffHours === 1 ? "" : "n"}`
        : `${diffHours} hour${diffHours === 1 ? "" : "s"} ago`;
    }
    if (diffDays < 7) {
      return language === "de"
        ? `Vor ${diffDays} Tag${diffDays === 1 ? "" : "en"}`
        : `${diffDays} day${diffDays === 1 ? "" : "s"} ago`;
    }
    return date.toLocaleDateString(language === "de" ? "de-DE" : "en-US", {
      day: "numeric",
      month: "short",
    });
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 z-40 transition-opacity"
        onClick={onClose}
      />

      {/* Drawer */}
      <div className="fixed right-0 top-0 h-full w-80 bg-[#1A2942] border-l border-white/10 z-50 flex flex-col shadow-xl">
        {/* Header */}
        <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-white">
            {language === "de" ? "Verlauf" : "History"}
          </h3>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-[#94A3B8] hover:text-white hover:bg-white/10 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {/* Loading */}
          {isLoading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 text-[#00D4AA] animate-spin" />
            </div>
          )}

          {/* Error */}
          {error && !isLoading && (
            <div className="p-4">
              <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
                <p className="text-red-400 text-sm">{error}</p>
              </div>
            </div>
          )}

          {/* Empty State */}
          {!isLoading && !error && artifacts.length === 0 && (
            <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
              <div className="w-12 h-12 bg-white/5 rounded-xl flex items-center justify-center mb-3">
                <FileImage className="w-6 h-6 text-[#64748B]" />
              </div>
              <p className="text-[#94A3B8] mb-1">
                {language === "de" ? "Keine Artefakte" : "No artifacts"}
              </p>
              <p className="text-[#64748B] text-sm">
                {language === "de"
                  ? "Generierte Skizzen erscheinen hier"
                  : "Generated sketches will appear here"}
              </p>
            </div>
          )}

          {/* Artifact List */}
          {!isLoading && artifacts.length > 0 && (
            <div className="py-2">
              {artifacts.map((artifact) => (
                <div
                  key={artifact.artifact_id}
                  onClick={() => {
                    onSelectArtifact(artifact);
                    onClose();
                  }}
                  className={`px-4 py-3 cursor-pointer transition-colors group ${
                    currentArtifactId === artifact.artifact_id
                      ? "bg-[#00D4AA]/10 border-l-2 border-[#00D4AA]"
                      : "hover:bg-white/5 border-l-2 border-transparent"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    {/* Type Icon */}
                    <div
                      className={`mt-0.5 ${
                        currentArtifactId === artifact.artifact_id
                          ? "text-[#00D4AA]"
                          : "text-[#64748B]"
                      }`}
                    >
                      {getTypeIcon(artifact.type)}
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <p
                        className={`text-sm font-medium truncate ${
                          currentArtifactId === artifact.artifact_id
                            ? "text-[#00D4AA]"
                            : "text-white"
                        }`}
                      >
                        {artifact.title}
                      </p>
                      <p className="text-xs text-[#64748B] mt-0.5 truncate">
                        {artifact.summary.substring(0, 60)}
                        {artifact.summary.length > 60 ? "..." : ""}
                      </p>
                      <div className="flex items-center gap-2 mt-1.5">
                        <span className="text-xs text-[#64748B]">
                          {formatDate(artifact.created_at)}
                        </span>
                        {artifact.trade_preset && (
                          <span className="px-1.5 py-0.5 bg-white/5 text-[#94A3B8] text-xs rounded">
                            {artifact.trade_preset}
                          </span>
                        )}
                        {artifact.version_number > 1 && (
                          <span className="px-1.5 py-0.5 bg-[#00D4AA]/10 text-[#00D4AA] text-xs rounded">
                            v{artifact.version_number}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={(e) => handleDelete(artifact.artifact_id, e)}
                        disabled={deletingId === artifact.artifact_id}
                        className="p-1.5 rounded text-[#64748B] hover:text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-50"
                        title={language === "de" ? "Löschen" : "Delete"}
                      >
                        {deletingId === artifact.artifact_id ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Trash2 className="w-3.5 h-3.5" />
                        )}
                      </button>
                      <ChevronRight className="w-4 h-4 text-[#64748B]" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        {artifacts.length > 0 && (
          <div className="px-4 py-3 border-t border-white/5 text-center">
            <p className="text-xs text-[#64748B]">
              {artifacts.length} {language === "de" ? "Artefakte" : "artifacts"}
            </p>
          </div>
        )}
      </div>
    </>
  );
}
