"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import { useDropzone } from "react-dropzone";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import {
  Upload,
  FileText,
  CheckCircle,
  AlertCircle,
  Download,
  ChevronRight,
  ChevronDown,
  Loader2,
  BarChart3,
  Table,
  Info,
  FileSpreadsheet,
  FileDown,
} from "lucide-react";
import {
  extractRooms,
  exportToExcel,
  exportToCSV,
  generateCSV,
  formatArea,
  formatNumber,
  getStyleDisplayName,
  type ExtractionResult,
  type ExtractedRoom,
} from "@/lib/api";
import { useLanguage } from "@/lib/i18n";

type Step = "upload" | "processing" | "results";
type ResultTab = "table" | "charts";

// Colors for categories
const CATEGORY_COLORS: Record<string, string> = {
  office: "#3B82F6",
  residential: "#10B981",
  circulation: "#F59E0B",
  stairs: "#8B5CF6",
  elevators: "#EC4899",
  shafts: "#6366F1",
  technical: "#14B8A6",
  sanitary: "#06B6D4",
  storage: "#84CC16",
  outdoor: "#22C55E",
  other: "#64748B",
};

type SortColumn = "room_number" | "room_name" | "category" | "area_m2" | "factor" | "counted_m2" | "page";
type SortDirection = "asc" | "desc";

export default function ScanPage() {
  const { t } = useLanguage();
  const [step, setStep] = useState<Step>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ExtractionResult | null>(null);
  const [selectedRoom, setSelectedRoom] = useState<ExtractedRoom | null>(null);
  const [activeTab, setActiveTab] = useState<ResultTab>("table");
  const [isExporting, setIsExporting] = useState(false);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const [sortColumn, setSortColumn] = useState<SortColumn>("room_number");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null);

  // Handle column sort
  const handleSort = (column: SortColumn) => {
    if (sortColumn === column) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc");
    } else {
      setSortColumn(column);
      setSortDirection("asc");
    }
  };

  // Get sorted and filtered rooms
  const getSortedRooms = () => {
    if (!result) return [];
    let rooms = [...result.rooms];

    // Filter by category
    if (categoryFilter) {
      rooms = rooms.filter(r => r.category === categoryFilter);
    }

    // Sort
    rooms.sort((a, b) => {
      let comparison = 0;
      switch (sortColumn) {
        case "room_number":
          comparison = a.room_number.localeCompare(b.room_number);
          break;
        case "room_name":
          comparison = a.room_name.localeCompare(b.room_name);
          break;
        case "category":
          comparison = a.category.localeCompare(b.category);
          break;
        case "area_m2":
          comparison = a.area_m2 - b.area_m2;
          break;
        case "factor":
          comparison = a.factor - b.factor;
          break;
        case "counted_m2":
          comparison = a.counted_m2 - b.counted_m2;
          break;
        case "page":
          comparison = a.page - b.page;
          break;
      }
      return sortDirection === "asc" ? comparison : -comparison;
    });

    return rooms;
  };

  // Check if a room is affected by revision clouds
  const isRoomAffectedByRevision = (roomNumber: string): boolean => {
    if (!result?.revision_clouds) return false;
    return result.revision_clouds.clouds.some(c =>
      c.affected_room_numbers.includes(roomNumber)
    );
  };

  // Handle file drop
  const onDrop = useCallback((acceptedFiles: File[]) => {
    const pdfFile = acceptedFiles.find(
      (f) => f.type === "application/pdf" || f.name.endsWith(".pdf")
    );
    if (pdfFile) {
      setFile(pdfFile);
      setError(null);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    multiple: false,
  });

  // Start extraction
  const handleStartExtraction = async () => {
    if (!file) return;

    setStep("processing");
    setError(null);

    try {
      const data = await extractRooms(file);
      setResult(data);
      setStep("results");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Extraction failed");
      setStep("upload");
    }
  };

  // Download helper
  const downloadBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Export to Excel
  const handleExportExcel = async () => {
    if (!result) return;
    setIsExporting(true);
    setShowExportMenu(false);
    try {
      const blob = await exportToExcel(result, file?.name || "SnapPlan Export");
      downloadBlob(blob, `${file?.name?.replace(".pdf", "") || "snapplan"}-export.xlsx`);
    } catch (err) {
      console.error("Excel export failed:", err);
    } finally {
      setIsExporting(false);
    }
  };

  // Export to CSV
  const handleExportCSV = async () => {
    if (!result) return;
    setIsExporting(true);
    setShowExportMenu(false);
    try {
      // Try backend first, fallback to client-side
      let blob: Blob;
      try {
        blob = await exportToCSV(result);
      } catch {
        blob = generateCSV(result);
      }
      downloadBlob(blob, `${file?.name?.replace(".pdf", "") || "snapplan"}-export.csv`);
    } catch (err) {
      console.error("CSV export failed:", err);
    } finally {
      setIsExporting(false);
    }
  };

  // Export to PDF (client-side table generation)
  const handleExportPDF = () => {
    if (!result) return;
    setShowExportMenu(false);

    // Create printable HTML
    const printContent = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>SnapPlan Export - ${file?.name || 'Report'}</title>
          <style>
            body { font-family: Arial, sans-serif; padding: 40px; }
            h1 { color: #0F1B2A; margin-bottom: 10px; }
            h2 { color: #64748B; font-weight: normal; margin-top: 0; }
            .summary { display: flex; gap: 40px; margin: 30px 0; padding: 20px; background: #f8fafc; border-radius: 8px; }
            .summary-item { }
            .summary-label { color: #64748B; font-size: 14px; }
            .summary-value { font-size: 28px; font-weight: bold; color: #0F1B2A; }
            table { width: 100%; border-collapse: collapse; margin-top: 20px; }
            th { background: #0F1B2A; color: white; text-align: left; padding: 12px 8px; font-size: 12px; }
            td { padding: 10px 8px; border-bottom: 1px solid #e2e8f0; font-size: 13px; }
            tr:nth-child(even) { background: #f8fafc; }
            .number { text-align: right; font-family: monospace; }
            .footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid #e2e8f0; color: #94A3B8; font-size: 12px; }
          </style>
        </head>
        <body>
          <h1>Room Area Report</h1>
          <h2>${file?.name || 'SnapPlan Export'}</h2>

          <div class="summary">
            <div class="summary-item">
              <div class="summary-label">Total Rooms</div>
              <div class="summary-value">${result.room_count}</div>
            </div>
            <div class="summary-item">
              <div class="summary-label">Total Area</div>
              <div class="summary-value">${result.total_area_m2.toFixed(2)} m²</div>
            </div>
            <div class="summary-item">
              <div class="summary-label">Counted Area</div>
              <div class="summary-value">${result.total_counted_m2.toFixed(2)} m²</div>
            </div>
          </div>

          <table>
            <thead>
              <tr>
                <th>Room Number</th>
                <th>Room Name</th>
                <th>Category</th>
                <th class="number">Area (m²)</th>
                <th class="number">Factor</th>
                <th class="number">Counted (m²)</th>
                <th class="number">Page</th>
              </tr>
            </thead>
            <tbody>
              ${result.rooms.map(room => `
                <tr>
                  <td>${room.room_number}</td>
                  <td>${room.room_name}</td>
                  <td>${t.common[room.category as keyof typeof t.common] || room.category}</td>
                  <td class="number">${room.area_m2.toFixed(2)}</td>
                  <td class="number">${(room.factor * 100).toFixed(0)}%</td>
                  <td class="number">${room.counted_m2.toFixed(2)}</td>
                  <td class="number">${room.page}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>

          <div class="footer">
            Generated by SnapPlan on ${new Date().toLocaleDateString('de-DE')} at ${new Date().toLocaleTimeString('de-DE')}
          </div>
        </body>
      </html>
    `;

    const printWindow = window.open('', '_blank');
    if (printWindow) {
      printWindow.document.write(printContent);
      printWindow.document.close();
      printWindow.print();
    }
  };

  // Reset and start over
  const handleReset = () => {
    setStep("upload");
    setFile(null);
    setResult(null);
    setSelectedRoom(null);
    setError(null);
  };

  // Prepare chart data
  const getCategoryChartData = () => {
    if (!result) return [];
    return Object.entries(result.totals_by_category)
      .map(([category, area]) => ({
        name: t.common[category as keyof typeof t.common] || category,
        value: area,
        color: CATEGORY_COLORS[category] || CATEGORY_COLORS.other,
      }))
      .sort((a, b) => b.value - a.value);
  };

  const getPageChartData = () => {
    if (!result) return [];
    const byPage: Record<number, number> = {};
    result.rooms.forEach((room) => {
      byPage[room.page] = (byPage[room.page] || 0) + room.area_m2;
    });
    return Object.entries(byPage).map(([page, area]) => ({
      name: `Page ${page}`,
      area,
    }));
  };

  return (
    <div className="max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white">{t.scan.title}</h1>
          <p className="text-[#94A3B8] mt-1">
            {t.scan.subtitle}
          </p>
        </div>
        {step === "results" && (
          <div className="flex items-center gap-3">
            <button
              onClick={handleReset}
              className="px-4 py-2.5 rounded-lg border border-white/10 text-[#94A3B8] hover:text-white hover:border-white/20 transition-colors"
            >
              {t.scan.newScan}
            </button>
            {/* Export Dropdown */}
            <div className="relative">
              <button
                onClick={() => setShowExportMenu(!showExportMenu)}
                disabled={isExporting}
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-[#00D4AA] text-[#0F1B2A] font-semibold hover:bg-[#00D4AA]/90 disabled:opacity-50 transition-colors"
              >
                {isExporting ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <Download className="w-5 h-5" />
                )}
                {t.scan.export}
                <ChevronDown className="w-4 h-4" />
              </button>
              {showExportMenu && (
                <div className="absolute right-0 mt-2 w-48 bg-[#1A2942] border border-white/10 rounded-lg shadow-xl z-50 overflow-hidden">
                  <button
                    onClick={handleExportExcel}
                    className="w-full flex items-center gap-3 px-4 py-3 text-left text-white hover:bg-white/5 transition-colors"
                  >
                    <FileSpreadsheet className="w-5 h-5 text-[#10B981]" />
                    <div>
                      <div className="font-medium">{t.scan.excel}</div>
                      <div className="text-xs text-[#64748B]">{t.scan.xlsxFile}</div>
                    </div>
                  </button>
                  <button
                    onClick={handleExportCSV}
                    className="w-full flex items-center gap-3 px-4 py-3 text-left text-white hover:bg-white/5 transition-colors border-t border-white/5"
                  >
                    <FileDown className="w-5 h-5 text-[#3B82F6]" />
                    <div>
                      <div className="font-medium">{t.scan.csv}</div>
                      <div className="text-xs text-[#64748B]">{t.scan.csvFile}</div>
                    </div>
                  </button>
                  <button
                    onClick={handleExportPDF}
                    className="w-full flex items-center gap-3 px-4 py-3 text-left text-white hover:bg-white/5 transition-colors border-t border-white/5"
                  >
                    <FileText className="w-5 h-5 text-[#EF4444]" />
                    <div>
                      <div className="font-medium">{t.scan.pdf}</div>
                      <div className="text-xs text-[#64748B]">{t.scan.printToPdf}</div>
                    </div>
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-4 mb-8">
        {[
          { key: "upload", label: t.scan.upload },
          { key: "processing", label: t.scan.processing },
          { key: "results", label: t.scan.results },
        ].map((s, i) => (
          <div key={s.key} className="flex items-center gap-4">
            <div
              className={`flex items-center gap-2 ${
                step === s.key
                  ? "text-[#00D4AA]"
                  : step === "results" || (step === "processing" && i < 1)
                    ? "text-white"
                    : "text-[#64748B]"
              }`}
            >
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                  step === s.key
                    ? "bg-[#00D4AA] text-[#0F1B2A]"
                    : step === "results" || (step === "processing" && i < 1)
                      ? "bg-[#00D4AA]/20 text-[#00D4AA]"
                      : "bg-[#1A2942] text-[#64748B]"
                }`}
              >
                {step === "results" || (step === "processing" && i < 1) ? (
                  <CheckCircle className="w-4 h-4" />
                ) : (
                  i + 1
                )}
              </div>
              <span className="font-medium">{s.label}</span>
            </div>
            {i < 2 && <ChevronRight className="w-5 h-5 text-[#64748B]" />}
          </div>
        ))}
      </div>

      {/* Error message */}
      {error && (
        <div className="mb-6 p-4 rounded-lg bg-red-500/10 border border-red-500/20 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-400 mt-0.5" />
          <div>
            <p className="text-sm text-red-400 font-medium">{t.scan.extractionFailed}</p>
            <p className="text-sm text-red-400/80 mt-1">{error}</p>
          </div>
        </div>
      )}

      {/* Upload Step */}
      {step === "upload" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Dropzone */}
          <div
            {...getRootProps()}
            className={`relative border-2 border-dashed rounded-xl p-12 text-center transition-all cursor-pointer ${
              isDragActive
                ? "border-[#00D4AA] bg-[#00D4AA]/5"
                : file
                  ? "border-[#00D4AA]/50 bg-[#00D4AA]/5"
                  : "border-white/20 hover:border-white/40"
            }`}
          >
            <input {...getInputProps()} />
            <div className="flex flex-col items-center">
              <div
                className={`w-20 h-20 rounded-full flex items-center justify-center mb-6 ${
                  file ? "bg-[#00D4AA]/20" : "bg-[#1A2942]"
                }`}
              >
                {file ? (
                  <FileText className="w-10 h-10 text-[#00D4AA]" />
                ) : (
                  <Upload className="w-10 h-10 text-[#94A3B8]" />
                )}
              </div>

              {file ? (
                <>
                  <h3 className="text-lg font-medium text-white mb-2">
                    {file.name}
                  </h3>
                  <p className="text-sm text-[#94A3B8]">
                    {(file.size / 1024 / 1024).toFixed(2)} MB
                  </p>
                  <p className="text-sm text-[#00D4AA] mt-2">
                    {t.scan.clickToReplace}
                  </p>
                </>
              ) : (
                <>
                  <h3 className="text-lg font-medium text-white mb-2">
                    {isDragActive ? t.scan.dropToUpload : t.scan.dropHere}
                  </h3>
                  <p className="text-sm text-[#64748B]">
                    {t.scan.supportFor}
                  </p>
                </>
              )}
            </div>
          </div>

          {/* Configuration Panel */}
          <div className="bg-[#1A2942] rounded-xl border border-white/5 p-6">
            <h2 className="text-lg font-semibold text-white mb-6">
              {t.scan.extractionSettings}
            </h2>

            <div className="space-y-6">
              {/* Auto-detect info */}
              <div className="p-4 rounded-lg bg-[#0F1B2A] border border-white/5">
                <div className="flex items-start gap-3">
                  <Info className="w-5 h-5 text-[#00D4AA] mt-0.5" />
                  <div>
                    <p className="text-sm text-white font-medium">
                      {t.scan.autoDetection}
                    </p>
                    <p className="text-xs text-[#94A3B8] mt-1">
                      {t.scan.autoDetectionDesc}
                    </p>
                  </div>
                </div>
              </div>

              {/* Supported pattern */}
              <div>
                <label className="block text-sm font-medium text-[#94A3B8] mb-3">
                  {t.scan.supportedPatterns}
                </label>
                <div className="space-y-2">
                  <div className="flex items-center justify-between p-3 rounded-lg bg-[#0F1B2A]">
                    <code className="text-[#00D4AA] font-mono text-sm">
                      NGF:
                    </code>
                    <span className="text-xs text-[#64748B]">{t.scan.ngfDescription}</span>
                  </div>
                </div>
              </div>

              <hr className="border-white/5" />

              {/* Start button */}
              <button
                onClick={handleStartExtraction}
                disabled={!file}
                className="w-full py-3 px-4 rounded-lg bg-[#00D4AA] text-[#0F1B2A] font-semibold hover:bg-[#00D4AA]/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
              >
                {t.scan.startExtraction}
                <ChevronRight className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Processing Step */}
      {step === "processing" && (
        <div className="flex flex-col items-center justify-center py-20">
          <div className="w-24 h-24 rounded-full bg-[#00D4AA]/10 flex items-center justify-center mb-6">
            <Loader2 className="w-12 h-12 text-[#00D4AA] animate-spin" />
          </div>
          <h2 className="text-xl font-semibold text-white mb-2">
            {t.scan.extractingRooms}
          </h2>
          <p className="text-[#94A3B8] text-center max-w-md">
            {t.scan.analyzing} {file?.name}...
            <br />
            {t.scan.usuallyTakes}
          </p>
        </div>
      )}

      {/* Results Step */}
      {step === "results" && result && (
        <div className="space-y-6">
          {/* Revision Cloud Warning */}
          {result.revision_clouds && result.revision_clouds.total_count > 0 && (
            <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4">
              <div className="flex items-start gap-3">
                <div className="flex-shrink-0 w-10 h-10 rounded-full bg-amber-500/20 flex items-center justify-center">
                  <svg className="w-5 h-5 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                </div>
                <div className="flex-1">
                  <h3 className="text-amber-500 font-semibold text-sm uppercase tracking-wider">
                    {t.scan.revisionClouds}
                  </h3>
                  <p className="text-amber-200/80 text-sm mt-1">
                    {result.revision_clouds.warning_message}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {result.revision_clouds.pages_with_clouds.map(page => (
                      <span key={page} className="px-2 py-1 bg-amber-500/20 rounded text-xs text-amber-300">
                        Page {page + 1}
                      </span>
                    ))}
                  </div>
                  {result.revision_clouds.clouds.some(c => c.affected_room_numbers.length > 0) && (
                    <div className="mt-3">
                      <p className="text-xs text-amber-300/70 mb-2">{t.scan.potentiallyAffected}</p>
                      <div className="flex flex-wrap gap-1">
                        {[...new Set(result.revision_clouds.clouds.flatMap(c => c.affected_room_numbers))].map(room => (
                          <span key={room} className="px-2 py-0.5 bg-amber-500/10 border border-amber-500/30 rounded text-xs text-amber-300 font-mono">
                            {room}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Summary Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-[#1A2942] rounded-xl p-5 border border-white/5">
              <p className="text-[#94A3B8] text-sm">{t.scan.rooms}</p>
              <p className="text-3xl font-bold text-white mt-1">
                {result.room_count}
              </p>
            </div>
            <div className="bg-[#1A2942] rounded-xl p-5 border border-white/5">
              <p className="text-[#94A3B8] text-sm">{t.scan.totalArea}</p>
              <p className="text-3xl font-bold text-white mt-1">
                {formatNumber(result.total_area_m2, 0)}
                <span className="text-lg text-[#94A3B8] ml-1">m²</span>
              </p>
            </div>
            <div className="bg-[#1A2942] rounded-xl p-5 border border-white/5">
              <p className="text-[#94A3B8] text-sm">{t.scan.countedArea}</p>
              <p className="text-3xl font-bold text-[#00D4AA] mt-1">
                {formatNumber(result.total_counted_m2, 0)}
                <span className="text-lg text-[#00D4AA]/70 ml-1">m²</span>
              </p>
            </div>
            <div className="bg-[#1A2942] rounded-xl p-5 border border-white/5">
              <p className="text-[#94A3B8] text-sm">{t.scan.blueprintStyle}</p>
              <p className="text-xl font-semibold text-white mt-1">
                {getStyleDisplayName(result.blueprint_style)}
              </p>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex items-center gap-2 border-b border-white/5 pb-4">
            <button
              onClick={() => setActiveTab("table")}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
                activeTab === "table"
                  ? "bg-[#00D4AA]/10 text-[#00D4AA]"
                  : "text-[#94A3B8] hover:text-white"
              }`}
            >
              <Table className="w-4 h-4" />
              {t.scan.schedule}
            </button>
            <button
              onClick={() => setActiveTab("charts")}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
                activeTab === "charts"
                  ? "bg-[#00D4AA]/10 text-[#00D4AA]"
                  : "text-[#94A3B8] hover:text-white"
              }`}
            >
              <BarChart3 className="w-4 h-4" />
              {t.scan.report}
            </button>
          </div>

          {/* Table View */}
          {activeTab === "table" && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Table */}
              <div className="lg:col-span-2 bg-[#1A2942] rounded-xl border border-white/5 overflow-hidden">
                {/* Filter Bar */}
                <div className="flex items-center justify-between px-4 py-3 border-b border-white/5 bg-[#0F1B2A]/50">
                  <div className="flex items-center gap-4">
                    <span className="text-sm text-[#64748B]">{t.scan.filter}</span>
                    <select
                      value={categoryFilter || ""}
                      onChange={(e) => setCategoryFilter(e.target.value || null)}
                      className="bg-[#1A2942] border border-white/10 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-[#00D4AA]"
                    >
                      <option value="">{t.scan.allCategories}</option>
                      {result && Object.keys(result.totals_by_category).map(cat => (
                        <option key={cat} value={cat} className="capitalize">{t.common[cat as keyof typeof t.common] || cat}</option>
                      ))}
                    </select>
                    {categoryFilter && (
                      <button
                        onClick={() => setCategoryFilter(null)}
                        className="text-xs text-[#00D4AA] hover:underline"
                      >
                        {t.scan.clearFilter}
                      </button>
                    )}
                  </div>
                  <span className="text-sm text-[#64748B]">
                    {getSortedRooms().length} {t.scan.roomsCount}
                    {categoryFilter && ` in ${t.common[categoryFilter as keyof typeof t.common] || categoryFilter}`}
                  </span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-white/5">
                        <th
                          onClick={() => handleSort("room_number")}
                          className="text-left text-xs font-medium text-[#64748B] uppercase tracking-wider px-4 py-3 cursor-pointer hover:text-white transition-colors select-none"
                        >
                          <span className="flex items-center gap-1">
                            {t.scan.room}
                            {sortColumn === "room_number" && (
                              <span className="text-[#00D4AA]">{sortDirection === "asc" ? "↑" : "↓"}</span>
                            )}
                          </span>
                        </th>
                        <th
                          onClick={() => handleSort("room_name")}
                          className="text-left text-xs font-medium text-[#64748B] uppercase tracking-wider px-4 py-3 cursor-pointer hover:text-white transition-colors select-none"
                        >
                          <span className="flex items-center gap-1">
                            {t.scan.name}
                            {sortColumn === "room_name" && (
                              <span className="text-[#00D4AA]">{sortDirection === "asc" ? "↑" : "↓"}</span>
                            )}
                          </span>
                        </th>
                        <th
                          onClick={() => handleSort("category")}
                          className="text-left text-xs font-medium text-[#64748B] uppercase tracking-wider px-4 py-3 cursor-pointer hover:text-white transition-colors select-none"
                        >
                          <span className="flex items-center gap-1">
                            {t.scan.category}
                            {sortColumn === "category" && (
                              <span className="text-[#00D4AA]">{sortDirection === "asc" ? "↑" : "↓"}</span>
                            )}
                          </span>
                        </th>
                        <th
                          onClick={() => handleSort("area_m2")}
                          className="text-right text-xs font-medium text-[#64748B] uppercase tracking-wider px-4 py-3 cursor-pointer hover:text-white transition-colors select-none"
                        >
                          <span className="flex items-center justify-end gap-1">
                            {t.scan.area}
                            {sortColumn === "area_m2" && (
                              <span className="text-[#00D4AA]">{sortDirection === "asc" ? "↑" : "↓"}</span>
                            )}
                          </span>
                        </th>
                        <th
                          onClick={() => handleSort("factor")}
                          className="text-right text-xs font-medium text-[#64748B] uppercase tracking-wider px-4 py-3 cursor-pointer hover:text-white transition-colors select-none"
                        >
                          <span className="flex items-center justify-end gap-1">
                            {t.scan.factor}
                            {sortColumn === "factor" && (
                              <span className="text-[#00D4AA]">{sortDirection === "asc" ? "↑" : "↓"}</span>
                            )}
                          </span>
                        </th>
                        <th
                          onClick={() => handleSort("counted_m2")}
                          className="text-right text-xs font-medium text-[#64748B] uppercase tracking-wider px-4 py-3 cursor-pointer hover:text-white transition-colors select-none"
                        >
                          <span className="flex items-center justify-end gap-1">
                            {t.scan.counted}
                            {sortColumn === "counted_m2" && (
                              <span className="text-[#00D4AA]">{sortDirection === "asc" ? "↑" : "↓"}</span>
                            )}
                          </span>
                        </th>
                        <th
                          onClick={() => handleSort("page")}
                          className="text-center text-xs font-medium text-[#64748B] uppercase tracking-wider px-4 py-3 cursor-pointer hover:text-white transition-colors select-none"
                        >
                          <span className="flex items-center justify-center gap-1">
                            {t.scan.page}
                            {sortColumn === "page" && (
                              <span className="text-[#00D4AA]">{sortDirection === "asc" ? "↑" : "↓"}</span>
                            )}
                          </span>
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {getSortedRooms().map((room, idx) => (
                        <tr
                          key={idx}
                          onClick={() => setSelectedRoom(room)}
                          className={`hover:bg-white/[0.02] cursor-pointer transition-colors ${
                            selectedRoom === room ? "bg-[#00D4AA]/5" : ""
                          } ${room.factor < 1 ? "bg-green-500/5" : ""} ${
                            isRoomAffectedByRevision(room.room_number) ? "bg-amber-500/10" : ""
                          }`}
                        >
                          <td className="px-4 py-3 text-sm font-mono text-[#00D4AA]">
                            <span className="flex items-center gap-2">
                              {room.room_number}
                              {isRoomAffectedByRevision(room.room_number) && (
                                <span title="Affected by revision cloud" className="text-amber-500">
                                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                                  </svg>
                                </span>
                              )}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-sm text-white">
                            {room.room_name}
                          </td>
                          <td className="px-4 py-3 text-sm text-[#94A3B8] capitalize">
                            {t.common[room.category as keyof typeof t.common] || room.category}
                          </td>
                          <td className="px-4 py-3 text-sm text-white text-right font-mono">
                            {formatNumber(room.area_m2)}
                          </td>
                          <td className="px-4 py-3 text-sm text-right">
                            {room.factor < 1 ? (
                              <span className="text-green-400">
                                {(room.factor * 100).toFixed(0)}%
                              </span>
                            ) : (
                              <span className="text-[#64748B]">100%</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-sm text-[#00D4AA] text-right font-mono font-medium">
                            {formatNumber(room.counted_m2)}
                          </td>
                          <td className="px-4 py-3 text-sm text-[#64748B] text-center">
                            {room.page}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Audit Panel */}
              <div className="bg-[#1A2942] rounded-xl border border-white/5 p-5">
                <h3 className="text-sm font-medium text-[#94A3B8] uppercase tracking-wider mb-4">
                  {t.scan.auditTrail}
                </h3>
                {selectedRoom ? (
                  <div className="space-y-4">
                    <div>
                      <p className="text-xs text-[#64748B]">{t.scan.roomNumber}</p>
                      <p className="text-white font-mono">
                        {selectedRoom.room_number}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-[#64748B]">{t.scan.roomName}</p>
                      <p className="text-white">{selectedRoom.room_name}</p>
                    </div>
                    <div>
                      <p className="text-xs text-[#64748B]">{t.scan.category}</p>
                      <p className="text-white">
                        {t.common[selectedRoom.category as keyof typeof t.common] || selectedRoom.category}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-[#64748B]">{t.scan.area}</p>
                      <p className="text-white font-mono">
                        {formatArea(selectedRoom.area_m2)}
                      </p>
                    </div>
                    <hr className="border-white/5" />
                    <div>
                      <p className="text-xs text-[#64748B] mb-2">{t.scan.sourceText}</p>
                      <pre className="text-xs text-[#00D4AA] font-mono bg-[#0F1B2A] p-3 rounded-lg overflow-x-auto">
                        {selectedRoom.source_text}
                      </pre>
                    </div>
                    <div>
                      <p className="text-xs text-[#64748B]">{t.scan.extractionPattern}</p>
                      <code className="text-xs text-[#F59E0B] font-mono">
                        {selectedRoom.extraction_pattern}
                      </code>
                    </div>
                    <div>
                      <p className="text-xs text-[#64748B]">{t.scan.page}</p>
                      <p className="text-white">{selectedRoom.page}</p>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-[#64748B]">
                    {t.scan.selectRoom}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Charts View */}
          {activeTab === "charts" && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Category Bar Chart */}
              <div className="bg-[#1A2942] rounded-xl border border-white/5 p-6">
                <h3 className="text-lg font-semibold text-white mb-4">
                  {t.scan.areaByCategory}
                </h3>
                <div className="h-80">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={getCategoryChartData()}
                      layout="vertical"
                      margin={{ top: 5, right: 30, left: 80, bottom: 5 }}
                    >
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="rgba(255,255,255,0.1)"
                      />
                      <XAxis
                        type="number"
                        tick={{ fill: "#94A3B8", fontSize: 12 }}
                        tickFormatter={(v) => `${v} m²`}
                      />
                      <YAxis
                        type="category"
                        dataKey="name"
                        tick={{ fill: "#94A3B8", fontSize: 12 }}
                        width={75}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "#1A2942",
                          border: "1px solid rgba(255,255,255,0.1)",
                          borderRadius: "8px",
                        }}
                        labelStyle={{ color: "#fff" }}
                        formatter={(value) => [
                          `${formatNumber(Number(value) || 0)} m²`,
                          "Area",
                        ]}
                      />
                      <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                        {getCategoryChartData().map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Category Pie Chart */}
              <div className="bg-[#1A2942] rounded-xl border border-white/5 p-6">
                <h3 className="text-lg font-semibold text-white mb-4">
                  {t.scan.distribution}
                </h3>
                <div className="h-80">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={getCategoryChartData()}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={100}
                        paddingAngle={2}
                        dataKey="value"
                      >
                        {getCategoryChartData().map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "#1A2942",
                          border: "1px solid rgba(255,255,255,0.1)",
                          borderRadius: "8px",
                        }}
                        formatter={(value) => [
                          `${formatNumber(Number(value) || 0)} m²`,
                          "Area",
                        ]}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                {/* Legend */}
                <div className="grid grid-cols-2 gap-2 mt-4">
                  {getCategoryChartData()
                    .slice(0, 6)
                    .map((entry) => (
                      <div key={entry.name} className="flex items-center gap-2">
                        <div
                          className="w-3 h-3 rounded-full"
                          style={{ backgroundColor: entry.color }}
                        />
                        <span className="text-xs text-[#94A3B8]">{entry.name}</span>
                      </div>
                    ))}
                </div>
              </div>

              {/* Page Distribution */}
              <div className="bg-[#1A2942] rounded-xl border border-white/5 p-6 lg:col-span-2">
                <h3 className="text-lg font-semibold text-white mb-4">
                  {t.scan.areaByPage}
                </h3>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={getPageChartData()}
                      margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
                    >
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="rgba(255,255,255,0.1)"
                      />
                      <XAxis
                        dataKey="name"
                        tick={{ fill: "#94A3B8", fontSize: 12 }}
                      />
                      <YAxis
                        tick={{ fill: "#94A3B8", fontSize: 12 }}
                        tickFormatter={(v) => `${v} m²`}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "#1A2942",
                          border: "1px solid rgba(255,255,255,0.1)",
                          borderRadius: "8px",
                        }}
                        formatter={(value) => [
                          `${formatNumber(Number(value) || 0)} m²`,
                          "Area",
                        ]}
                      />
                      <Bar dataKey="area" fill="#00D4AA" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          )}

          {/* Warnings */}
          {result.warnings.length > 0 && (
            <div className="bg-[#F59E0B]/10 rounded-xl border border-[#F59E0B]/20 p-4">
              <h3 className="text-sm font-medium text-[#F59E0B] mb-2">
                {t.scan.warnings}
              </h3>
              <ul className="space-y-1">
                {result.warnings.map((warning, idx) => (
                  <li key={idx} className="text-sm text-[#F59E0B]/80">
                    {warning}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
