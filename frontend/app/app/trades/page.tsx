"use client";

import { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import {
  Upload,
  FileText,
  CheckCircle,
  AlertCircle,
  Download,
  ChevronRight,
  ChevronDown,
  Loader2,
  Table,
  Info,
  Calculator,
  Layers,
  Droplet,
  Grid3X3,
  Building2,
  HardHat,
  DoorOpen,
  Paintbrush,
  Zap,
  Wind,
  LayoutGrid,
  PanelTop,
} from "lucide-react";
import {
  extractRooms,
  formatArea,
  formatNumber,
  type ExtractionResult,
} from "@/lib/api";
import {
  calculateProjection,
  exportProjectionJson,
  downloadBlob,
  formatQuantity,
  getConfidenceColor,
  getConfidenceLabel,
  TRADE_DISPLAY,
  detectDrywallFromSymbols,
  type TradeType,
  type ProjectionResult,
  type ProjectionParams,
  type AufmassItem,
  type ProjectedMaterial,
  type DrywallDetectionResult,
  type LegendSymbol,
} from "@/lib/trade-projection";
import { useLanguage } from "@/lib/i18n";

type Step = "select-trade" | "upload" | "configure" | "processing" | "results";

// Extended trade type for UI (includes new trades not yet in backend)
type ExtendedTradeType = TradeType | "raised_floor" | "electrical" | "doors" | "facade" | "painting" | "hls";

// Trades that have backend support for projection
const SUPPORTED_TRADES: TradeType[] = ["scaffolding", "drywall", "screed", "floor_finish", "waterproofing"];

// Check if a trade has backend projection support
const isTradeSupported = (trade: ExtendedTradeType): trade is TradeType => {
  return SUPPORTED_TRADES.includes(trade as TradeType);
};

// Trade icons mapping
const TRADE_ICONS: Record<ExtendedTradeType, React.ReactNode> = {
  scaffolding: <HardHat className="w-8 h-8" />,
  drywall: <Layers className="w-8 h-8" />,
  screed: <Grid3X3 className="w-8 h-8" />,
  floor_finish: <Building2 className="w-8 h-8" />,
  waterproofing: <Droplet className="w-8 h-8" />,
  raised_floor: <LayoutGrid className="w-8 h-8" />,
  electrical: <Zap className="w-8 h-8" />,
  doors: <DoorOpen className="w-8 h-8" />,
  facade: <PanelTop className="w-8 h-8" />,
  painting: <Paintbrush className="w-8 h-8" />,
  hls: <Wind className="w-8 h-8" />,
};

// Trade feature keys mapping
const TRADE_FEATURE_KEYS: Record<ExtendedTradeType, string> = {
  scaffolding: "scaffoldingFeatures",
  drywall: "drywallFeatures",
  screed: "screedFeatures",
  floor_finish: "flooringFeatures",
  waterproofing: "waterproofingFeatures",
  raised_floor: "raisedFloorFeatures",
  electrical: "electricalFeatures",
  doors: "doorsFeatures",
  facade: "facadeFeatures",
  painting: "paintingFeatures",
  hls: "hlsFeatures",
};

// Drywall detection mode
type DrywallMode = "estimation" | "detection";

export default function TradesPage() {
  const { t } = useLanguage();
  const [step, setStep] = useState<Step>("select-trade");
  const [selectedTrade, setSelectedTrade] = useState<ExtendedTradeType | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [extractionResult, setExtractionResult] = useState<ExtractionResult | null>(null);
  const [projectionResult, setProjectionResult] = useState<ProjectionResult | null>(null);
  const [drywallDetectionResult, setDrywallDetectionResult] = useState<DrywallDetectionResult | null>(null);
  const [drywallMode, setDrywallMode] = useState<DrywallMode>("detection"); // Default to detection
  const [error, setError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [showExportMenu, setShowExportMenu] = useState(false);

  // Trade-specific parameters
  const [params, setParams] = useState<ProjectionParams>({
    waste_factor: 1.10,
    wall_height_m: 2.8,
    scaffold_height_m: 10,
    screed_thickness_mm: 50,
    stud_spacing_mm: 625,
    scaffold_type: "standard",
    drywall_system: "single",
    screed_type: "ct",
    finish_type: "laminate",
    waterproofing_type: "liquid",
    waterproofing_wall_height_m: 2.0,
  });

  // File upload handling
  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    const pdfFile = acceptedFiles[0];
    if (!pdfFile) return;

    setFile(pdfFile);
    setError(null);

    // For drywall with detection mode, skip room extraction
    if (selectedTrade === "drywall" && drywallMode === "detection") {
      setStep("configure");
      return;
    }

    // Extract rooms from PDF
    try {
      const result = await extractRooms(pdfFile);
      setExtractionResult(result);
      setStep("configure");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to extract from PDF");
      setStep("upload");
    }
  }, [selectedTrade, drywallMode]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    maxFiles: 1,
  });

  // Calculate projection
  const handleCalculate = async () => {
    // For drywall with detection mode, use Plankopf-based detection
    if (selectedTrade === "drywall" && drywallMode === "detection" && file) {
      setStep("processing");
      setError(null);

      try {
        const result = await detectDrywallFromSymbols(file, {
          wall_height_m: params.wall_height_m || 2.8,
        });
        setDrywallDetectionResult(result);
        setStep("results");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Drywall detection failed");
        setStep("configure");
      }
      return;
    }

    // Standard projection flow
    if (!selectedTrade || !extractionResult) return;

    // Check if trade is supported
    if (!isTradeSupported(selectedTrade)) {
      setError("This trade is coming soon! Projection not yet available.");
      return;
    }

    setStep("processing");
    setError(null);

    try {
      const result = await calculateProjection({
        extraction_result: extractionResult as unknown as Record<string, unknown>,
        trade_type: selectedTrade,
        params,
        use_llm: false,
      });
      setProjectionResult(result);
      setStep("results");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Projection calculation failed");
      setStep("configure");
    }
  };

  // Export handlers
  const handleExportJson = async () => {
    if (!projectionResult) return;
    setIsExporting(true);
    try {
      const blob = await exportProjectionJson(projectionResult);
      const filename = `projection_${selectedTrade}_${new Date().toISOString().split("T")[0]}.json`;
      downloadBlob(blob, filename);
    } catch (err) {
      setError("Export failed");
    } finally {
      setIsExporting(false);
      setShowExportMenu(false);
    }
  };

  // Reset to start
  const handleReset = () => {
    setStep("select-trade");
    setSelectedTrade(null);
    setFile(null);
    setExtractionResult(null);
    setProjectionResult(null);
    setDrywallDetectionResult(null);
    setError(null);
  };

  // Get required params for selected trade
  const getRequiredParams = (): string[] => {
    if (!selectedTrade) return [];
    switch (selectedTrade) {
      case "scaffolding":
        return ["scaffold_height_m"];
      case "drywall":
        return ["wall_height_m"];
      case "screed":
        return ["screed_thickness_mm"];
      case "floor_finish":
        return ["finish_type"];
      case "waterproofing":
        return [];
      default:
        return [];
    }
  };

  // Helper function to get translated trade name or description
  const getTradeTranslation = (trade: ExtendedTradeType, type: "name" | "desc"): string => {
    const tradeTranslations: Record<ExtendedTradeType, { name: string; desc: string }> = {
      scaffolding: { name: t.trades.scaffolding, desc: t.trades.scaffoldingDesc },
      drywall: { name: t.trades.drywall, desc: t.trades.drywallDesc },
      screed: { name: t.trades.screed, desc: t.trades.screedDesc },
      floor_finish: { name: t.trades.flooring, desc: t.trades.flooringDesc },
      waterproofing: { name: t.trades.waterproofing, desc: t.trades.waterproofingDesc },
      raised_floor: { name: t.trades.raisedFloor, desc: t.trades.raisedFloorDesc },
      electrical: { name: t.trades.electrical, desc: t.trades.electricalDesc },
      doors: { name: t.trades.doors, desc: t.trades.doorsDesc },
      facade: { name: t.trades.facade, desc: t.trades.facadeDesc },
      painting: { name: t.trades.painting, desc: t.trades.paintingDesc },
      hls: { name: t.trades.hls, desc: t.trades.hlsDesc },
    };
    return tradeTranslations[trade][type];
  };

  // Helper function to get trade-specific features
  const getTradeFeatures = (trade: ExtendedTradeType): string[] => {
    const featureMap: Record<ExtendedTradeType, string[]> = {
      scaffolding: t.trades.scaffoldingFeatures,
      drywall: t.trades.drywallFeatures,
      screed: t.trades.screedFeatures,
      floor_finish: t.trades.flooringFeatures,
      waterproofing: t.trades.waterproofingFeatures,
      raised_floor: t.trades.raisedFloorFeatures,
      electrical: t.trades.electricalFeatures,
      doors: t.trades.doorsFeatures,
      facade: t.trades.facadeFeatures,
      painting: t.trades.paintingFeatures,
      hls: t.trades.hlsFeatures,
    };
    return featureMap[trade] || [];
  };

  return (
    <div className="max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white">{t.trades.title}</h1>
          <p className="text-[#94A3B8] mt-1">
            {t.trades.subtitle}
          </p>
        </div>
        {step !== "select-trade" && (
          <button
            onClick={handleReset}
            className="px-4 py-2 text-[#94A3B8] hover:text-white transition-colors"
          >
            Start Over
          </button>
        )}
      </div>

      {/* Step Indicator */}
      <div className="flex items-center gap-4 mb-8">
        {[
          { key: "select-trade", label: t.trades.selectTrade },
          { key: "upload", label: t.trades.uploadPDF },
          { key: "configure", label: t.trades.configure },
          { key: "results", label: t.trades.results },
        ].map((s, i) => {
          const isActive = step === s.key || (step === "processing" && s.key === "results");
          const isPast =
            (step === "upload" && i === 0) ||
            (step === "configure" && i <= 1) ||
            (step === "processing" && i <= 2) ||
            (step === "results" && i <= 2);

          return (
            <div key={s.key} className="flex items-center">
              <div
                className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-[#00D4AA]/10 text-[#00D4AA]"
                    : isPast
                    ? "bg-[#00D4AA]/5 text-[#00D4AA]/60"
                    : "bg-white/5 text-[#64748B]"
                }`}
              >
                {isPast && !isActive ? (
                  <CheckCircle className="w-4 h-4" />
                ) : (
                  <span className="w-5 h-5 rounded-full bg-current/20 flex items-center justify-center text-xs">
                    {i + 1}
                  </span>
                )}
                {s.label}
              </div>
              {i < 3 && <ChevronRight className="w-4 h-4 text-[#64748B] mx-2" />}
            </div>
          );
        })}
      </div>

      {/* Error Display */}
      {error && (
        <div className="mb-6 p-4 bg-red-500/10 border border-red-500/20 rounded-lg flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-400" />
          <p className="text-red-400">{error}</p>
        </div>
      )}

      {/* Step 1: Select Trade */}
      {step === "select-trade" && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {([
            { key: "drywall" as ExtendedTradeType, name: t.trades.drywall, desc: t.trades.drywallDesc },
            { key: "screed" as ExtendedTradeType, name: t.trades.screed, desc: t.trades.screedDesc },
            { key: "floor_finish" as ExtendedTradeType, name: t.trades.flooring, desc: t.trades.flooringDesc },
            { key: "doors" as ExtendedTradeType, name: t.trades.doors, desc: t.trades.doorsDesc },
            { key: "raised_floor" as ExtendedTradeType, name: t.trades.raisedFloor, desc: t.trades.raisedFloorDesc },
            { key: "electrical" as ExtendedTradeType, name: t.trades.electrical, desc: t.trades.electricalDesc },
            { key: "facade" as ExtendedTradeType, name: t.trades.facade, desc: t.trades.facadeDesc },
            { key: "painting" as ExtendedTradeType, name: t.trades.painting, desc: t.trades.paintingDesc },
            { key: "hls" as ExtendedTradeType, name: t.trades.hls, desc: t.trades.hlsDesc },
            { key: "waterproofing" as ExtendedTradeType, name: t.trades.waterproofing, desc: t.trades.waterproofingDesc },
            { key: "scaffolding" as ExtendedTradeType, name: t.trades.scaffolding, desc: t.trades.scaffoldingDesc },
          ]).map((trade) => (
            <button
              key={trade.key}
              onClick={() => {
                setSelectedTrade(trade.key);
                setStep("upload");
              }}
              className="p-5 bg-[#1A2942] rounded-xl border border-white/5 hover:border-[#00D4AA]/30 transition-all text-left group"
            >
              <div className="flex items-center gap-3 mb-2">
                <div className="p-2.5 rounded-lg bg-white/5 text-[#00D4AA] group-hover:bg-[#00D4AA]/10 transition-colors">
                  {TRADE_ICONS[trade.key]}
                </div>
                <h3 className="text-base font-semibold text-white">{trade.name}</h3>
              </div>
              <p className="text-sm text-[#64748B]">{trade.desc}</p>
            </button>
          ))}
        </div>
      )}

      {/* Step 2: Upload PDF */}
      {step === "upload" && selectedTrade && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Dropzone */}
          <div
            {...getRootProps()}
            className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-all ${
              isDragActive
                ? "border-[#00D4AA] bg-[#00D4AA]/5"
                : "border-white/10 hover:border-[#00D4AA]/50 bg-[#1A2942]"
            }`}
          >
            <input {...getInputProps()} />
            <Upload
              className={`w-12 h-12 mx-auto mb-4 ${
                isDragActive ? "text-[#00D4AA]" : "text-[#64748B]"
              }`}
            />
            <p className="text-white font-medium mb-2">
              {isDragActive ? "Drop the PDF here" : "Drag & drop a PDF blueprint"}
            </p>
            <p className="text-[#64748B] text-sm">or click to browse files</p>
          </div>

          {/* Trade Info Card */}
          <div className="bg-[#1A2942] rounded-xl border border-white/5 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 rounded-lg bg-[#00D4AA]/10 text-[#00D4AA]">
                {TRADE_ICONS[selectedTrade]}
              </div>
              <div>
                <h3 className="text-lg font-semibold text-white">
                  {getTradeTranslation(selectedTrade, "name")}
                </h3>
                <p className="text-sm text-[#64748B]">
                  {getTradeTranslation(selectedTrade, "desc")}
                </p>
              </div>
            </div>

            {/* Drywall Detection Mode Toggle */}
            {selectedTrade === "drywall" && (
              <div className="border-t border-white/5 pt-4 mt-4">
                <h4 className="text-sm font-medium text-white mb-3">Erkennungsmethode:</h4>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={() => setDrywallMode("detection")}
                    className={`p-3 rounded-lg border text-left transition-all ${
                      drywallMode === "detection"
                        ? "border-[#00D4AA] bg-[#00D4AA]/10"
                        : "border-white/10 bg-white/5 hover:bg-white/10"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <Layers className="w-4 h-4 text-[#00D4AA]" />
                      <span className="text-white font-medium text-sm">Symbol-Erkennung</span>
                    </div>
                    <p className="text-xs text-[#64748B]">
                      Liest Plankopf-Legende für Trockenbauwände
                    </p>
                  </button>
                  <button
                    onClick={() => setDrywallMode("estimation")}
                    className={`p-3 rounded-lg border text-left transition-all ${
                      drywallMode === "estimation"
                        ? "border-[#00D4AA] bg-[#00D4AA]/10"
                        : "border-white/10 bg-white/5 hover:bg-white/10"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <Calculator className="w-4 h-4 text-yellow-400" />
                      <span className="text-white font-medium text-sm">Schätzung</span>
                    </div>
                    <p className="text-xs text-[#64748B]">
                      Berechnet aus Raumperimetern (U: Werte)
                    </p>
                  </button>
                </div>
                {drywallMode === "detection" && (
                  <div className="mt-3 p-2 rounded bg-[#00D4AA]/10 border border-[#00D4AA]/30">
                    <p className="text-xs text-[#00D4AA]">
                      Diese Methode liest den Plankopf, um Trockenbauwand-Muster zu erkennen und scannt dann die Zeichnung.
                    </p>
                  </div>
                )}
              </div>
            )}

            <div className="border-t border-white/5 pt-4 mt-4">
              <h4 className="text-sm font-medium text-white mb-3">{t.trades.whatYouGet}</h4>
              <ul className="space-y-2 text-sm text-[#94A3B8]">
                {getTradeFeatures(selectedTrade).map((feature, idx) => (
                  <li key={idx} className="flex items-center gap-2">
                    <CheckCircle className={`w-4 h-4 ${
                      idx === 0 ? "text-[#00D4AA]" :
                      idx === 1 ? "text-green-400" :
                      idx === 2 ? "text-blue-400" : "text-yellow-400"
                    }`} />
                    {feature}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Step 3: Configure Parameters */}
      {step === "configure" && selectedTrade && (extractionResult || (selectedTrade === "drywall" && drywallMode === "detection" && file)) && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Parameters Form */}
          <div className="lg:col-span-2 bg-[#1A2942] rounded-xl border border-white/5 p-6">
            <h3 className="text-lg font-semibold text-white mb-4">
              Configure Parameters
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Common: Waste Factor */}
              <div>
                <label className="block text-sm font-medium text-[#94A3B8] mb-1">
                  Waste Factor
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="1"
                  max="2"
                  value={params.waste_factor}
                  onChange={(e) =>
                    setParams({ ...params, waste_factor: parseFloat(e.target.value) || 1.1 })
                  }
                  className="w-full bg-[#0F1B2A] border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#00D4AA]"
                />
                <p className="text-xs text-[#64748B] mt-1">1.10 = 10% waste allowance</p>
              </div>

              {/* Scaffolding params */}
              {selectedTrade === "scaffolding" && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-[#94A3B8] mb-1">
                      Scaffold Height (m) *
                    </label>
                    <input
                      type="number"
                      step="0.5"
                      min="1"
                      value={params.scaffold_height_m || ""}
                      onChange={(e) =>
                        setParams({ ...params, scaffold_height_m: parseFloat(e.target.value) })
                      }
                      className="w-full bg-[#0F1B2A] border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#00D4AA]"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-[#94A3B8] mb-1">
                      Scaffold Type
                    </label>
                    <select
                      value={params.scaffold_type}
                      onChange={(e) =>
                        setParams({ ...params, scaffold_type: e.target.value as "standard" | "rollgeruest" | "fassade" })
                      }
                      className="w-full bg-[#0F1B2A] border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#00D4AA]"
                    >
                      <option value="standard">Standard Facade</option>
                      <option value="rollgeruest">Mobile Scaffold</option>
                      <option value="fassade">Heavy-duty Facade</option>
                    </select>
                  </div>
                </>
              )}

              {/* Drywall params */}
              {selectedTrade === "drywall" && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-[#94A3B8] mb-1">
                      Wall Height (m) *
                    </label>
                    <input
                      type="number"
                      step="0.1"
                      min="2"
                      max="5"
                      value={params.wall_height_m || ""}
                      onChange={(e) =>
                        setParams({ ...params, wall_height_m: parseFloat(e.target.value) })
                      }
                      className="w-full bg-[#0F1B2A] border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#00D4AA]"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-[#94A3B8] mb-1">
                      Drywall System
                    </label>
                    <select
                      value={params.drywall_system}
                      onChange={(e) =>
                        setParams({ ...params, drywall_system: e.target.value as "single" | "double" | "fire_rated" })
                      }
                      className="w-full bg-[#0F1B2A] border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#00D4AA]"
                    >
                      <option value="single">Single Layer (CW 50)</option>
                      <option value="double">Double Layer (CW 75)</option>
                      <option value="fire_rated">Fire Rated F90 (CW 100)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-[#94A3B8] mb-1">
                      Stud Spacing (mm)
                    </label>
                    <select
                      value={params.stud_spacing_mm}
                      onChange={(e) =>
                        setParams({ ...params, stud_spacing_mm: parseInt(e.target.value) })
                      }
                      className="w-full bg-[#0F1B2A] border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#00D4AA]"
                    >
                      <option value={417}>417mm (High load)</option>
                      <option value={625}>625mm (Standard)</option>
                    </select>
                  </div>
                </>
              )}

              {/* Screed params */}
              {selectedTrade === "screed" && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-[#94A3B8] mb-1">
                      Screed Thickness (mm) *
                    </label>
                    <input
                      type="number"
                      step="5"
                      min="30"
                      max="100"
                      value={params.screed_thickness_mm || ""}
                      onChange={(e) =>
                        setParams({ ...params, screed_thickness_mm: parseInt(e.target.value) })
                      }
                      className="w-full bg-[#0F1B2A] border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#00D4AA]"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-[#94A3B8] mb-1">
                      Screed Type
                    </label>
                    <select
                      value={params.screed_type}
                      onChange={(e) =>
                        setParams({ ...params, screed_type: e.target.value as "ct" | "ca" | "ma" })
                      }
                      className="w-full bg-[#0F1B2A] border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#00D4AA]"
                    >
                      <option value="ct">Cement Screed (CT)</option>
                      <option value="ca">Anhydrite Screed (CA)</option>
                      <option value="ma">Mastic Asphalt (MA)</option>
                    </select>
                  </div>
                </>
              )}

              {/* Floor finish params */}
              {selectedTrade === "floor_finish" && (
                <div>
                  <label className="block text-sm font-medium text-[#94A3B8] mb-1">
                    Floor Finish Type *
                  </label>
                  <select
                    value={params.finish_type}
                    onChange={(e) =>
                      setParams({ ...params, finish_type: e.target.value as "laminate" | "parquet" | "tile" | "carpet" })
                    }
                    className="w-full bg-[#0F1B2A] border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#00D4AA]"
                  >
                    <option value="laminate">Laminate</option>
                    <option value="parquet">Parquet</option>
                    <option value="tile">Tile</option>
                    <option value="carpet">Carpet</option>
                  </select>
                </div>
              )}

              {/* Waterproofing params */}
              {selectedTrade === "waterproofing" && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-[#94A3B8] mb-1">
                      Waterproofing Type
                    </label>
                    <select
                      value={params.waterproofing_type}
                      onChange={(e) =>
                        setParams({ ...params, waterproofing_type: e.target.value as "liquid" | "membrane" | "bitumen" })
                      }
                      className="w-full bg-[#0F1B2A] border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#00D4AA]"
                    >
                      <option value="liquid">Liquid Membrane</option>
                      <option value="membrane">Sheet Membrane</option>
                      <option value="bitumen">Bitumen</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-[#94A3B8] mb-1">
                      Wall Height in Wet Areas (m)
                    </label>
                    <input
                      type="number"
                      step="0.1"
                      min="1"
                      max="3"
                      value={params.waterproofing_wall_height_m || 2.0}
                      onChange={(e) =>
                        setParams({ ...params, waterproofing_wall_height_m: parseFloat(e.target.value) })
                      }
                      className="w-full bg-[#0F1B2A] border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#00D4AA]"
                    />
                  </div>
                </>
              )}
            </div>

            <div className="mt-6 flex justify-end">
              <button
                onClick={handleCalculate}
                className="px-6 py-2.5 bg-[#00D4AA] text-[#0F1B2A] font-semibold rounded-lg hover:bg-[#00D4AA]/90 transition-colors flex items-center gap-2"
              >
                <Calculator className="w-4 h-4" />
                Calculate Projection
              </button>
            </div>
          </div>

          {/* Extraction Summary OR Detection Mode Info */}
          <div className="bg-[#1A2942] rounded-xl border border-white/5 p-6">
            {selectedTrade === "drywall" && drywallMode === "detection" ? (
              <>
                <h3 className="text-lg font-semibold text-white mb-4">
                  Symbol Detection Mode
                </h3>
                <div className="space-y-3">
                  <div className="p-3 rounded-lg bg-[#00D4AA]/10 border border-[#00D4AA]/30">
                    <div className="flex items-center gap-2 mb-2">
                      <Layers className="w-5 h-5 text-[#00D4AA]" />
                      <span className="text-[#00D4AA] font-medium">Plankopf Detection</span>
                    </div>
                    <p className="text-xs text-[#94A3B8]">
                      Will analyze the legend/title block to learn drywall patterns, then scan the drawing.
                    </p>
                  </div>
                  <div className="text-sm text-[#94A3B8]">
                    <p className="mb-2">What happens:</p>
                    <ol className="list-decimal list-inside space-y-1 text-xs">
                      <li>Parse Plankopf (legend area)</li>
                      <li>Find &quot;Trockenbau&quot; symbols</li>
                      <li>Scan drawing for matching patterns</li>
                      <li>Measure length and calculate area</li>
                    </ol>
                  </div>
                </div>
              </>
            ) : extractionResult ? (
              <>
                <h3 className="text-lg font-semibold text-white mb-4">
                  Extraction Summary
                </h3>
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-[#94A3B8]">Total Area</span>
                    <span className="text-white font-medium">
                      {formatArea(extractionResult.total_area_m2)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[#94A3B8]">Counted Area</span>
                    <span className="text-white font-medium">
                      {formatArea(extractionResult.total_counted_m2)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[#94A3B8]">Rooms</span>
                    <span className="text-white font-medium">
                      {extractionResult.room_count}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[#94A3B8]">Blueprint Style</span>
                    <span className="text-white font-medium">
                      {extractionResult.blueprint_style}
                    </span>
                  </div>
                </div>
              </>
            ) : null}

            {file && (
              <div className="mt-4 pt-4 border-t border-white/5">
                <div className="flex items-center gap-2 text-sm text-[#64748B]">
                  <FileText className="w-4 h-4" />
                  {file.name}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Step 4: Processing */}
      {step === "processing" && (
        <div className="flex flex-col items-center justify-center py-20">
          <Loader2 className="w-12 h-12 text-[#00D4AA] animate-spin mb-4" />
          <p className="text-white font-medium mb-2">Calculating projection...</p>
          <p className="text-[#64748B] text-sm">This may take a few seconds</p>
        </div>
      )}

      {/* Step 5: Results - Projection Mode */}
      {step === "results" && projectionResult && (
        <div className="space-y-6">
          {/* Results Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="p-2 rounded-lg bg-[#00D4AA]/10 text-[#00D4AA]">
                {selectedTrade && TRADE_ICONS[selectedTrade]}
              </div>
              <div>
                <h2 className="text-xl font-semibold text-white">
                  {projectionResult.trade_name_de}
                </h2>
                <p className="text-sm text-[#64748B]">
                  {projectionResult.aufmass_items.length} Aufmass items, {projectionResult.projected_materials.length} materials
                </p>
              </div>
            </div>

            {/* Export Button */}
            <div className="relative">
              <button
                onClick={() => setShowExportMenu(!showExportMenu)}
                disabled={isExporting}
                className="px-4 py-2.5 bg-[#00D4AA] text-[#0F1B2A] font-semibold rounded-lg hover:bg-[#00D4AA]/90 transition-colors flex items-center gap-2"
              >
                {isExporting ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Download className="w-4 h-4" />
                )}
                Export
                <ChevronDown className="w-4 h-4" />
              </button>

              {showExportMenu && (
                <div className="absolute right-0 mt-2 w-48 bg-[#1A2942] rounded-lg border border-white/10 shadow-xl z-10">
                  <button
                    onClick={handleExportJson}
                    className="w-full px-4 py-2 text-left text-white hover:bg-white/5 flex items-center gap-2"
                  >
                    <FileText className="w-4 h-4" />
                    Export JSON
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Warnings */}
          {projectionResult.warnings.length > 0 && (
            <div className="p-4 bg-yellow-500/10 border border-yellow-500/20 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <AlertCircle className="w-5 h-5 text-yellow-400" />
                <span className="text-yellow-400 font-medium">Warnings</span>
              </div>
              <ul className="list-disc list-inside text-sm text-yellow-300/80">
                {projectionResult.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Aufmass Items Table */}
          <div className="bg-[#1A2942] rounded-xl border border-white/5 overflow-hidden">
            <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between">
              <h3 className="font-semibold text-white flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-green-400" />
                Aufmass (Ground Truth)
              </h3>
              <span className="text-xs text-[#64748B]">
                Calculated from measured quantities
              </span>
            </div>
            <table className="w-full">
              <thead>
                <tr className="bg-white/5">
                  <th className="px-4 py-2 text-left text-xs font-medium text-[#64748B]">Pos.</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-[#64748B]">Description</th>
                  <th className="px-4 py-2 text-right text-xs font-medium text-[#64748B]">Quantity</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-[#64748B]">Unit</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-[#64748B]">Formula</th>
                </tr>
              </thead>
              <tbody>
                {projectionResult.aufmass_items.map((item: AufmassItem) => (
                  <tr key={item.item_id} className="border-t border-white/5 hover:bg-white/5">
                    <td className="px-4 py-3 text-sm text-[#94A3B8]">{item.position}</td>
                    <td className="px-4 py-3 text-sm text-white">{item.description}</td>
                    <td className="px-4 py-3 text-sm text-white text-right font-medium">
                      {formatQuantity(item.quantity)}
                    </td>
                    <td className="px-4 py-3 text-sm text-[#94A3B8]">{item.unit}</td>
                    <td className="px-4 py-3 text-xs text-[#64748B] font-mono">{item.formula}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Projected Materials Table */}
          <div className="bg-[#1A2942] rounded-xl border border-white/5 overflow-hidden">
            <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between">
              <h3 className="font-semibold text-white flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-yellow-400" />
                Projected Materials (Estimates)
              </h3>
              <span className="text-xs text-[#64748B]">
                Based on assumptions - verify before ordering
              </span>
            </div>
            <table className="w-full">
              <thead>
                <tr className="bg-white/5">
                  <th className="px-4 py-2 text-left text-xs font-medium text-[#64748B]">Material</th>
                  <th className="px-4 py-2 text-right text-xs font-medium text-[#64748B]">Quantity</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-[#64748B]">Unit</th>
                  <th className="px-4 py-2 text-center text-xs font-medium text-[#64748B]">Confidence</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-[#64748B]">Assumptions</th>
                </tr>
              </thead>
              <tbody>
                {projectionResult.projected_materials.map((mat: ProjectedMaterial) => (
                  <tr key={mat.material_id} className="border-t border-white/5 hover:bg-white/5">
                    <td className="px-4 py-3 text-sm text-white">{mat.name}</td>
                    <td className="px-4 py-3 text-sm text-white text-right font-medium">
                      {formatQuantity(mat.effective_quantity)}
                    </td>
                    <td className="px-4 py-3 text-sm text-[#94A3B8]">{mat.unit}</td>
                    <td className="px-4 py-3 text-center">
                      <span
                        className={`px-2 py-0.5 rounded-full text-xs font-medium border ${getConfidenceColor(
                          mat.confidence_level
                        )}`}
                      >
                        {getConfidenceLabel(mat.confidence_level)} ({Math.round(mat.confidence * 100)}%)
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <ul className="text-xs text-[#64748B] list-disc list-inside">
                        {mat.assumptions.slice(0, 2).map((a, i) => (
                          <li key={i}>{a}</li>
                        ))}
                        {mat.assumptions.length > 2 && (
                          <li className="text-[#00D4AA]">+{mat.assumptions.length - 2} more</li>
                        )}
                      </ul>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Disclaimer */}
          <div className="p-4 bg-blue-500/10 border border-blue-500/20 rounded-lg">
            <div className="flex items-start gap-3">
              <Info className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-blue-300/80">{projectionResult.disclaimer}</p>
            </div>
          </div>
        </div>
      )}

      {/* Step 5: Results - Drywall Detection Mode */}
      {step === "results" && drywallDetectionResult && (
        <div className="space-y-6">
          {/* Results Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="p-2 rounded-lg bg-[#00D4AA]/10 text-[#00D4AA]">
                <Layers className="w-8 h-8" />
              </div>
              <div>
                <h2 className="text-xl font-semibold text-white">
                  Drywall Symbol Detection
                </h2>
                <p className="text-sm text-[#64748B]">
                  {drywallDetectionResult.grand_total_segments} segments detected, {formatQuantity(drywallDetectionResult.grand_total_area_m2)} m² total
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                drywallDetectionResult.plankopf_found
                  ? "bg-green-500/20 text-green-400"
                  : "bg-yellow-500/20 text-yellow-400"
              }`}>
                {drywallDetectionResult.plankopf_found ? "Plankopf Found" : "No Plankopf"}
              </span>
            </div>
          </div>

          {/* Summary Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-[#1A2942] rounded-xl p-5 border border-white/5">
              <p className="text-[#94A3B8] text-sm">Total Length</p>
              <p className="text-2xl font-bold text-white mt-1">
                {formatQuantity(drywallDetectionResult.grand_total_length_m)} <span className="text-lg text-[#94A3B8]">m</span>
              </p>
            </div>
            <div className="bg-[#1A2942] rounded-xl p-5 border border-white/5">
              <p className="text-[#94A3B8] text-sm">Total Area</p>
              <p className="text-2xl font-bold text-[#00D4AA] mt-1">
                {formatQuantity(drywallDetectionResult.grand_total_area_m2)} <span className="text-lg text-[#00D4AA]/70">m²</span>
              </p>
            </div>
            <div className="bg-[#1A2942] rounded-xl p-5 border border-white/5">
              <p className="text-[#94A3B8] text-sm">Segments</p>
              <p className="text-2xl font-bold text-white mt-1">
                {drywallDetectionResult.grand_total_segments}
              </p>
            </div>
            <div className="bg-[#1A2942] rounded-xl p-5 border border-white/5">
              <p className="text-[#94A3B8] text-sm">Wall Height</p>
              <p className="text-2xl font-bold text-white mt-1">
                {drywallDetectionResult.wall_height_m} <span className="text-lg text-[#94A3B8]">m</span>
              </p>
            </div>
          </div>

          {/* Warnings */}
          {drywallDetectionResult.warnings.length > 0 && (
            <div className="p-4 bg-yellow-500/10 border border-yellow-500/20 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <AlertCircle className="w-5 h-5 text-yellow-400" />
                <span className="text-yellow-400 font-medium">Warnings</span>
              </div>
              <ul className="list-disc list-inside text-sm text-yellow-300/80">
                {drywallDetectionResult.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Legend Symbols Found */}
          {drywallDetectionResult.legend_symbols.length > 0 && (
            <div className="bg-[#1A2942] rounded-xl border border-white/5 overflow-hidden">
              <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between">
                <h3 className="font-semibold text-white flex items-center gap-2">
                  <CheckCircle className="w-4 h-4 text-[#00D4AA]" />
                  Legend Symbols (Plankopf)
                </h3>
                <span className="text-xs text-[#64748B]">
                  Found on page {(drywallDetectionResult.plankopf_page ?? 0) + 1}
                </span>
              </div>
              <div className="p-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {drywallDetectionResult.legend_symbols.map((symbol: LegendSymbol) => (
                  <div
                    key={symbol.symbol_id}
                    className={`p-3 rounded-lg border ${
                      symbol.material_type === "drywall"
                        ? "bg-[#00D4AA]/10 border-[#00D4AA]/30"
                        : "bg-white/5 border-white/10"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <div className="w-6 h-6 rounded bg-gray-600 flex items-center justify-center text-xs">
                        {symbol.pattern_info.pattern_type === "hatching" ? "///" :
                         symbol.pattern_info.pattern_type === "crosshatch" ? "X" :
                         symbol.pattern_info.pattern_type === "solid_fill" ? "█" : "?"}
                      </div>
                      <span className="text-white font-medium text-sm truncate">{symbol.label}</span>
                    </div>
                    <div className="text-xs text-[#64748B]">
                      {symbol.material_type && (
                        <span className={`inline-block px-1.5 py-0.5 rounded mr-2 ${
                          symbol.material_type === "drywall" ? "bg-[#00D4AA]/20 text-[#00D4AA]" : "bg-white/10"
                        }`}>
                          {symbol.material_type}
                        </span>
                      )}
                      <span>{symbol.pattern_info.pattern_type}</span>
                      {symbol.pattern_info.hatching_angle && (
                        <span className="ml-2">{symbol.pattern_info.hatching_angle.toFixed(0)}°</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Drywall Results */}
          {drywallDetectionResult.drywall_results.length > 0 ? (
            drywallDetectionResult.drywall_results.map((result) => (
              <div key={result.detection_id} className="bg-[#1A2942] rounded-xl border border-white/5 overflow-hidden">
                <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between">
                  <h3 className="font-semibold text-white flex items-center gap-2">
                    <Layers className="w-4 h-4 text-[#00D4AA]" />
                    {result.material_label}
                  </h3>
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-[#94A3B8]">
                      {formatQuantity(result.total_length_m)} m × {result.wall_height_m}m =
                    </span>
                    <span className="text-[#00D4AA] font-bold">
                      {formatQuantity(result.total_area_m2)} m²
                    </span>
                  </div>
                </div>
                <table className="w-full">
                  <thead>
                    <tr className="bg-white/5">
                      <th className="px-4 py-2 text-left text-xs font-medium text-[#64748B]">Segment</th>
                      <th className="px-4 py-2 text-right text-xs font-medium text-[#64748B]">Length (m)</th>
                      <th className="px-4 py-2 text-right text-xs font-medium text-[#64748B]">Area (m²)</th>
                      <th className="px-4 py-2 text-center text-xs font-medium text-[#64748B]">Page</th>
                      <th className="px-4 py-2 text-center text-xs font-medium text-[#64748B]">Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.segments.slice(0, 20).map((seg) => (
                      <tr key={seg.segment_id} className="border-t border-white/5 hover:bg-white/5">
                        <td className="px-4 py-2 text-sm text-[#94A3B8] font-mono">{seg.segment_id}</td>
                        <td className="px-4 py-2 text-sm text-white text-right">{formatQuantity(seg.length_m)}</td>
                        <td className="px-4 py-2 text-sm text-[#00D4AA] text-right font-medium">{formatQuantity(seg.area_m2)}</td>
                        <td className="px-4 py-2 text-sm text-[#64748B] text-center">{seg.page_number + 1}</td>
                        <td className="px-4 py-2 text-center">
                          <span className={`px-2 py-0.5 rounded-full text-xs ${
                            seg.confidence >= 0.8 ? "bg-green-500/20 text-green-400" :
                            seg.confidence >= 0.5 ? "bg-yellow-500/20 text-yellow-400" :
                            "bg-red-500/20 text-red-400"
                          }`}>
                            {Math.round(seg.confidence * 100)}%
                          </span>
                        </td>
                      </tr>
                    ))}
                    {result.segments.length > 20 && (
                      <tr className="border-t border-white/5">
                        <td colSpan={5} className="px-4 py-2 text-center text-sm text-[#64748B]">
                          ... and {result.segments.length - 20} more segments
                        </td>
                      </tr>
                    )}
                  </tbody>
                  <tfoot>
                    <tr className="border-t border-white/10 bg-white/5">
                      <td className="px-4 py-2 text-sm font-medium text-white">Total</td>
                      <td className="px-4 py-2 text-sm font-bold text-white text-right">{formatQuantity(result.total_length_m)}</td>
                      <td className="px-4 py-2 text-sm font-bold text-[#00D4AA] text-right">{formatQuantity(result.total_area_m2)}</td>
                      <td colSpan={2}></td>
                    </tr>
                  </tfoot>
                </table>
                {result.assumptions.length > 0 && (
                  <div className="px-4 py-3 border-t border-white/5 bg-white/[0.02]">
                    <p className="text-xs text-[#64748B] mb-1">Assumptions:</p>
                    <ul className="text-xs text-[#94A3B8] list-disc list-inside">
                      {result.assumptions.map((a, i) => <li key={i}>{a}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            ))
          ) : (
            <div className="bg-[#1A2942] rounded-xl border border-white/5 p-8 text-center">
              <AlertCircle className="w-12 h-12 text-yellow-400 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-white mb-2">No Drywall Detected</h3>
              <p className="text-[#94A3B8] text-sm max-w-md mx-auto">
                No drywall patterns matching the legend symbols were found in the drawing.
                This could mean the blueprint doesn&apos;t contain drywall or the patterns are
                different from standard hatching styles.
              </p>
            </div>
          )}

          {/* Info Note */}
          <div className="p-4 bg-blue-500/10 border border-blue-500/20 rounded-lg">
            <div className="flex items-start gap-3">
              <Info className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-blue-300/80">
                This analysis reads the Plankopf (legend/title block) to learn material patterns, then detects matching
                patterns in the drawing. Results are based on vector pattern matching and may require verification.
                Wall area = detected length × wall height ({drywallDetectionResult.wall_height_m}m).
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
