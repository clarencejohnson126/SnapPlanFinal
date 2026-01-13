"use client";

import { useState, useEffect } from "react";
import { Loader2, Wand2, ChevronDown, Sparkles, Zap } from "lucide-react";
import { useLanguage } from "@/lib/i18n";
import type { ArtifactContext, PromptTemplate } from "@/lib/artifact-api";
import { getTemplates } from "@/lib/artifact-api";

const TRADE_PRESETS = [
  { id: "flooring", label_de: "Oberbelag", label_en: "Flooring" },
  { id: "drywall", label_de: "Trockenbau", label_en: "Drywall" },
  { id: "electrical", label_de: "Elektro", label_en: "Electrical" },
  { id: "insulation", label_de: "Dämmung", label_en: "Insulation" },
  { id: "doors", label_de: "Türen", label_en: "Doors" },
];

interface PromptPanelProps {
  onGenerate: (prompt: string, trade?: string, context?: ArtifactContext) => void;
  isGenerating: boolean;
}

export function PromptPanel({ onGenerate, isGenerating }: PromptPanelProps) {
  const { language } = useLanguage();
  const [prompt, setPrompt] = useState("");
  const [trade, setTrade] = useState<string | undefined>();
  const [context, setContext] = useState<ArtifactContext>({});
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [showContext, setShowContext] = useState(false);
  const [loadingTemplates, setLoadingTemplates] = useState(true);

  // Load templates on mount
  useEffect(() => {
    getTemplates()
      .then((data) => {
        setTemplates(data.templates);
        setLoadingTemplates(false);
      })
      .catch((err) => {
        console.error("Failed to load templates:", err);
        setLoadingTemplates(false);
      });
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim() || isGenerating) return;
    onGenerate(prompt, trade, context);
  };

  const applyTemplate = (template: PromptTemplate) => {
    setPrompt(template.prompt);
    setTrade(template.trade);
  };

  const clearForm = () => {
    setPrompt("");
    setTrade(undefined);
    setContext({});
  };

  return (
    <div className="h-full flex flex-col bg-[#1A2942] rounded-xl border border-white/5 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-[#00D4AA]" />
          <h2 className="text-lg font-semibold text-white">
            {language === "de" ? "Skizze generieren" : "Generate Sketch"}
          </h2>
        </div>
        {(prompt || trade) && (
          <button
            onClick={clearForm}
            className="text-xs text-[#64748B] hover:text-[#94A3B8] transition-colors"
          >
            {language === "de" ? "Zurücksetzen" : "Clear"}
          </button>
        )}
      </div>

      {/* Quick Templates */}
      <div className="px-4 py-3 border-b border-white/5 bg-white/[0.02]">
        <p className="text-xs text-[#64748B] mb-2">
          {language === "de" ? "Schnellvorlagen:" : "Quick templates:"}
        </p>
        {loadingTemplates ? (
          <div className="flex items-center gap-2 text-[#64748B]">
            <Loader2 className="w-3 h-3 animate-spin" />
            <span className="text-xs">Loading...</span>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {templates.map((t) => (
              <button
                key={t.id}
                onClick={() => applyTemplate(t)}
                disabled={isGenerating}
                className={`px-2.5 py-1.5 text-xs rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5 ${
                  t.interactive
                    ? "bg-[#00D4AA]/10 hover:bg-[#00D4AA]/20 text-[#00D4AA] hover:text-white border border-[#00D4AA]/30"
                    : "bg-white/5 hover:bg-white/10 text-[#94A3B8] hover:text-white"
                }`}
                title={t.interactive ? (language === "de" ? "Interaktives Detail mit Ton und Animation" : "Interactive detail with sound and animation") : undefined}
              >
                {t.interactive && <Zap className="w-3 h-3" />}
                {language === "de" ? t.name_de : t.name_en}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="flex-1 flex flex-col p-4 gap-4 overflow-y-auto">
        {/* Prompt Textarea */}
        <div className="flex-1 min-h-0">
          <label className="block text-sm font-medium text-[#94A3B8] mb-1.5">
            {language === "de" ? "Beschreibung" : "Description"}
          </label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder={
              language === "de"
                ? "Beschreiben Sie das gewünschte Baudetail...\n\nBeispiel: Erstelle einen Schnitt durch eine Trockenbauwand mit Dämmung und Beplankung."
                : "Describe the construction detail you need...\n\nExample: Create a cross-section of a drywall partition with insulation."
            }
            disabled={isGenerating}
            className="w-full h-full min-h-[120px] bg-[#0F1B2A] border border-white/10 rounded-lg px-3 py-2.5 text-white placeholder-[#64748B] focus:outline-none focus:border-[#00D4AA] resize-none disabled:opacity-50 text-sm"
          />
        </div>

        {/* Trade Preset Dropdown */}
        <div>
          <label className="block text-sm font-medium text-[#94A3B8] mb-1.5">
            {language === "de" ? "Gewerk" : "Trade"}
          </label>
          <select
            value={trade || ""}
            onChange={(e) => setTrade(e.target.value || undefined)}
            disabled={isGenerating}
            className="w-full bg-[#0F1B2A] border border-white/10 rounded-lg px-3 py-2.5 text-white focus:outline-none focus:border-[#00D4AA] disabled:opacity-50 text-sm appearance-none cursor-pointer"
            style={{
              backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2394A3B8'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E")`,
              backgroundRepeat: "no-repeat",
              backgroundPosition: "right 12px center",
              backgroundSize: "16px",
            }}
          >
            <option value="">
              {language === "de" ? "Kein Gewerk ausgewählt" : "No trade selected"}
            </option>
            {TRADE_PRESETS.map((t) => (
              <option key={t.id} value={t.id}>
                {language === "de" ? t.label_de : t.label_en}
              </option>
            ))}
          </select>
        </div>

        {/* Collapsible Context Fields */}
        <div>
          <button
            type="button"
            onClick={() => setShowContext(!showContext)}
            className="flex items-center gap-2 text-sm text-[#94A3B8] hover:text-white transition-colors"
          >
            <ChevronDown
              className={`w-4 h-4 transition-transform duration-200 ${
                showContext ? "rotate-180" : ""
              }`}
            />
            {language === "de" ? "Kontext hinzufügen" : "Add context"}
            {Object.values(context).some(Boolean) && (
              <span className="ml-1 px-1.5 py-0.5 bg-[#00D4AA]/20 text-[#00D4AA] text-xs rounded">
                {Object.values(context).filter(Boolean).length}
              </span>
            )}
          </button>

          {showContext && (
            <div className="mt-3 grid grid-cols-2 gap-3">
              <input
                type="text"
                placeholder={language === "de" ? "Projekt" : "Project"}
                value={context.project || ""}
                onChange={(e) => setContext({ ...context, project: e.target.value })}
                disabled={isGenerating}
                className="bg-[#0F1B2A] border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-[#64748B] focus:outline-none focus:border-[#00D4AA] disabled:opacity-50"
              />
              <input
                type="text"
                placeholder={language === "de" ? "Geschoss" : "Floor"}
                value={context.floor || ""}
                onChange={(e) => setContext({ ...context, floor: e.target.value })}
                disabled={isGenerating}
                className="bg-[#0F1B2A] border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-[#64748B] focus:outline-none focus:border-[#00D4AA] disabled:opacity-50"
              />
              <input
                type="text"
                placeholder={language === "de" ? "Achse/Raster" : "Grid/Axis"}
                value={context.grid_axis || ""}
                onChange={(e) => setContext({ ...context, grid_axis: e.target.value })}
                disabled={isGenerating}
                className="bg-[#0F1B2A] border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-[#64748B] focus:outline-none focus:border-[#00D4AA] disabled:opacity-50"
              />
              <input
                type="text"
                placeholder={language === "de" ? "Wand-ID" : "Wall ID"}
                value={context.wall_id || ""}
                onChange={(e) => setContext({ ...context, wall_id: e.target.value })}
                disabled={isGenerating}
                className="bg-[#0F1B2A] border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-[#64748B] focus:outline-none focus:border-[#00D4AA] disabled:opacity-50"
              />
            </div>
          )}
        </div>

        {/* Submit Button */}
        <button
          type="submit"
          disabled={!prompt.trim() || isGenerating}
          className="w-full py-3 bg-[#00D4AA] text-[#0F1B2A] font-semibold rounded-lg hover:bg-[#00D4AA]/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
        >
          {isGenerating ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              {language === "de" ? "Generiere..." : "Generating..."}
            </>
          ) : (
            <>
              <Wand2 className="w-5 h-5" />
              {language === "de" ? "Skizze generieren" : "Generate Sketch"}
            </>
          )}
        </button>
      </form>
    </div>
  );
}
