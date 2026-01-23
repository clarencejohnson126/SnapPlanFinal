"use client";

import { useState, useCallback, useMemo } from "react";
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
  Table as TableIcon,
  Info,
  FileSpreadsheet,
  DoorClosed,
  BarChart3,
  ArrowUpDown,
} from "lucide-react";
import {
  extractDoors,
  formatNumber,
  type DoorExtractionResult,
  type ExtractedDoor,
} from "@/lib/api";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Legend,
  Tooltip,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";

type Step = "upload" | "processing" | "results";
type ViewMode = "table" | "charts";
type SortField = "door_number" | "fire_rating" | "section" | "confidence" | "width";
type SortDirection = "asc" | "desc";

export default function DoorsPage() {
  const [step, setStep] = useState<Step>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DoorExtractionResult | null>(null);
  const [selectedDoor, setSelectedDoor] = useState<ExtractedDoor | null>(null);
  const [pageNumber, setPageNumber] = useState<number | undefined>(undefined);
  const [scale, setScale] = useState<number | undefined>(undefined);
  const [viewMode, setViewMode] = useState<ViewMode>("table");
  const [sortField, setSortField] = useState<SortField>("door_number");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");

  // Extract section from door number (e.g., "B.00.1.003-1" → "B.00.1")
  const getSection = (doorNumber?: string): string => {
    if (!doorNumber) return "Unknown";
    const match = doorNumber.match(/^([A-Z]+\.\d{2}\.\d+)/);
    return match ? match[1] : "Unknown";
  };

  // Sort and prepare doors data
  const sortedDoors = useMemo(() => {
    if (!result) return [];

    const doorsWithSection = result.doors.map(door => ({
      ...door,
      section: getSection(door.door_number)
    }));

    return [...doorsWithSection].sort((a, b) => {
      let compareValue = 0;

      switch (sortField) {
        case "door_number":
          compareValue = (a.door_number || "").localeCompare(b.door_number || "");
          break;
        case "fire_rating":
          compareValue = (a.fire_rating || "").localeCompare(b.fire_rating || "");
          break;
        case "section":
          compareValue = a.section.localeCompare(b.section);
          break;
        case "confidence":
          compareValue = a.confidence - b.confidence;
          break;
        case "width":
          compareValue = (a.width_m || 0) - (b.width_m || 0);
          break;
      }

      return sortDirection === "asc" ? compareValue : -compareValue;
    });
  }, [result, sortField, sortDirection]);

  // Prepare fire rating chart data
  const fireRatingData = useMemo(() => {
    if (!result) return [];

    const ratingCounts: Record<string, number> = {};
    result.doors.forEach(door => {
      const rating = door.fire_rating || "Standard";
      ratingCounts[rating] = (ratingCounts[rating] || 0) + 1;
    });

    return Object.entries(ratingCounts).map(([name, value]) => ({
      name,
      value,
    }));
  }, [result]);

  // Prepare section chart data
  const sectionData = useMemo(() => {
    if (!result) return [];

    const sectionCounts: Record<string, number> = {};
    result.doors.forEach(door => {
      const section = getSection(door.door_number);
      sectionCounts[section] = (sectionCounts[section] || 0) + 1;
    });

    return Object.entries(sectionCounts)
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [result]);

  // Chart colors
  const FIRE_RATING_COLORS: Record<string, string> = {
    "T30": "#00D4AA",
    "T90": "#F59E0B",
    "DSS": "#EF4444",
    "Standard": "#64748B",
  };

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDirection("asc");
    }
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
      const data = await extractDoors(file, pageNumber, scale);
      setResult(data);
      setStep("results");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Door extraction failed");
      setStep("upload");
    }
  };

  // Reset and start over
  const handleReset = () => {
    setStep("upload");
    setFile(null);
    setResult(null);
    setSelectedDoor(null);
    setError(null);
  };

  // Download CSV
  const handleDownloadCSV = () => {
    if (!result) return;

    const headers = ['Door Number', 'Type', 'Width (m)', 'Height (m)', 'Fire Rating', 'Page', 'Confidence', 'Method'];
    const rows = result.doors.map(door => [
      door.door_number || '-',
      door.door_type || '-',
      door.width_m?.toFixed(2) || '-',
      door.height_m?.toFixed(2) || '-',
      door.fire_rating || '-',
      door.page_number.toString(),
      door.confidence.toFixed(2),
      door.extraction_method,
    ]);

    const csvContent = [headers.join(','), ...rows.map(row => row.map(cell => `"${cell}"`).join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${file?.name?.replace(".pdf", "") || "door-extraction"}-doors.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="flex items-center gap-3">
            <DoorClosed className="w-8 h-8 text-[#00D4AA]" />
            <h1 className="text-2xl font-bold text-white">Door Extraction</h1>
          </div>
          <p className="text-[#94A3B8] mt-1">
            Extract doors from floor plans using label + geometry detection
          </p>
        </div>
        {step === "results" && (
          <div className="flex items-center gap-3">
            <button
              onClick={handleReset}
              className="px-4 py-2.5 rounded-lg border border-white/10 text-[#94A3B8] hover:text-white hover:border-white/20 transition-colors"
            >
              New Scan
            </button>
            <button
              onClick={handleDownloadCSV}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-[#00D4AA] text-[#0F1B2A] font-semibold hover:bg-[#00D4AA]/90 transition-colors"
            >
              <Download className="w-5 h-5" />
              Export CSV
            </button>
          </div>
        )}
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-4 mb-8">
        {[
          { key: "upload", label: "Upload" },
          { key: "processing", label: "Processing" },
          { key: "results", label: "Results" },
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
            <p className="text-sm text-red-400 font-medium">Extraction Failed</p>
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
                    Click to replace
                  </p>
                </>
              ) : (
                <>
                  <h3 className="text-lg font-medium text-white mb-2">
                    {isDragActive ? "Drop to upload" : "Drop floor plan here"}
                  </h3>
                  <p className="text-sm text-[#64748B]">
                    PDF floor plans with door annotations
                  </p>
                </>
              )}
            </div>
          </div>

          {/* Configuration Panel */}
          <div className="bg-[#1A2942] rounded-xl border border-white/5 p-6">
            <h2 className="text-lg font-semibold text-white mb-6">
              Extraction Settings
            </h2>

            <div className="space-y-6">
              {/* Info box */}
              <div className="p-4 rounded-lg bg-[#0F1B2A] border border-white/5">
                <div className="flex items-start gap-3">
                  <Info className="w-5 h-5 text-[#00D4AA] mt-0.5" />
                  <div>
                    <p className="text-sm text-white font-medium">
                      4-Stage Pipeline
                    </p>
                    <p className="text-xs text-[#94A3B8] mt-1">
                      Label detection → Geometry detection → Association → Attribute extraction
                    </p>
                  </div>
                </div>
              </div>

              {/* Page number */}
              <div>
                <label className="block text-sm font-medium text-[#94A3B8] mb-2">
                  Page Number (optional)
                </label>
                <input
                  type="number"
                  min="1"
                  value={pageNumber || ''}
                  onChange={(e) => setPageNumber(e.target.value ? parseInt(e.target.value) : undefined)}
                  placeholder="All pages"
                  className="w-full px-3 py-2 bg-[#0F1B2A] border border-white/10 rounded-lg text-white placeholder:text-[#64748B] focus:outline-none focus:border-[#00D4AA]"
                />
              </div>

              {/* Scale */}
              <div>
                <label className="block text-sm font-medium text-[#94A3B8] mb-2">
                  Scale (optional)
                </label>
                <input
                  type="number"
                  min="1"
                  value={scale || ''}
                  onChange={(e) => setScale(e.target.value ? parseInt(e.target.value) : undefined)}
                  placeholder="e.g., 100 for 1:100"
                  className="w-full px-3 py-2 bg-[#0F1B2A] border border-white/10 rounded-lg text-white placeholder:text-[#64748B] focus:outline-none focus:border-[#00D4AA]"
                />
              </div>

              {/* Supported patterns */}
              <div>
                <label className="block text-sm font-medium text-[#94A3B8] mb-3">
                  Detected Patterns
                </label>
                <div className="space-y-2">
                  <div className="flex items-center justify-between p-3 rounded-lg bg-[#0F1B2A]">
                    <code className="text-[#00D4AA] font-mono text-sm">B.00.1.003-1</code>
                    <span className="text-xs text-[#64748B]">Door numbers</span>
                  </div>
                  <div className="flex items-center justify-between p-3 rounded-lg bg-[#0F1B2A]">
                    <code className="text-[#00D4AA] font-mono text-sm">T30, T90, DSS</code>
                    <span className="text-xs text-[#64748B]">Fire ratings</span>
                  </div>
                  <div className="flex items-center justify-between p-3 rounded-lg bg-[#0F1B2A]">
                    <code className="text-[#00D4AA] font-mono text-sm">0,90 x 2,10</code>
                    <span className="text-xs text-[#64748B]">Dimensions</span>
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
                Start Door Extraction
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
            Extracting Doors...
          </h2>
          <p className="text-[#94A3B8] text-center max-w-md">
            Analyzing {file?.name}...
            <br />
            Detecting labels and door geometries
          </p>
        </div>
      )}

      {/* Results Step */}
      {step === "results" && result && (
        <div className="space-y-6">
          {/* Summary Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-[#1A2942] rounded-xl p-5 border border-white/5">
              <p className="text-[#94A3B8] text-sm">Total Doors</p>
              <p className="text-3xl font-bold text-white mt-1">
                {result.total_doors}
              </p>
            </div>
            <div className="bg-[#1A2942] rounded-xl p-5 border border-white/5">
              <p className="text-[#94A3B8] text-sm">Avg Width</p>
              <p className="text-3xl font-bold text-white mt-1">
                {result.summary.avg_width_m?.toFixed(2) || '-'}
                <span className="text-lg text-[#94A3B8] ml-1">m</span>
              </p>
            </div>
            <div className="bg-[#1A2942] rounded-xl p-5 border border-white/5">
              <p className="text-[#94A3B8] text-sm">Pages</p>
              <p className="text-3xl font-bold text-white mt-1">
                {result.processed_pages.length}
              </p>
            </div>
            <div className="bg-[#1A2942] rounded-xl p-5 border border-white/5">
              <p className="text-[#94A3B8] text-sm">Processing Time</p>
              <p className="text-3xl font-bold text-[#00D4AA] mt-1">
                {(result.extraction_time_ms / 1000).toFixed(1)}
                <span className="text-lg text-[#00D4AA]/70 ml-1">s</span>
              </p>
            </div>
          </div>

          {/* Warnings */}
          {result.warnings.length > 0 && (
            <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4">
              <h3 className="text-sm font-medium text-amber-500 mb-2">Warnings</h3>
              <ul className="space-y-1">
                {result.warnings.map((warning, idx) => (
                  <li key={idx} className="text-sm text-amber-200/80">
                    {warning}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* View Mode Tabs */}
          <div className="flex items-center gap-2 bg-[#1A2942] rounded-lg p-1 border border-white/5 w-fit">
            <button
              onClick={() => setViewMode("table")}
              className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                viewMode === "table"
                  ? "bg-[#00D4AA] text-[#0F1B2A]"
                  : "text-[#94A3B8] hover:text-white"
              }`}
            >
              <TableIcon className="w-4 h-4" />
              Table View
            </button>
            <button
              onClick={() => setViewMode("charts")}
              className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                viewMode === "charts"
                  ? "bg-[#00D4AA] text-[#0F1B2A]"
                  : "text-[#94A3B8] hover:text-white"
              }`}
            >
              <BarChart3 className="w-4 h-4" />
              Charts View
            </button>
          </div>

          {/* Table View */}
          {viewMode === "table" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 bg-[#1A2942] rounded-xl border border-white/5 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-white/5">
                      <th className="text-left text-xs font-medium text-[#64748B] uppercase tracking-wider px-4 py-3">
                        <button
                          onClick={() => handleSort("door_number")}
                          className="flex items-center gap-1 hover:text-white transition-colors"
                        >
                          Door Number
                          <ArrowUpDown className="w-3 h-3" />
                        </button>
                      </th>
                      <th className="text-left text-xs font-medium text-[#64748B] uppercase tracking-wider px-4 py-3">
                        <button
                          onClick={() => handleSort("section")}
                          className="flex items-center gap-1 hover:text-white transition-colors"
                        >
                          Section
                          <ArrowUpDown className="w-3 h-3" />
                        </button>
                      </th>
                      <th className="text-right text-xs font-medium text-[#64748B] uppercase tracking-wider px-4 py-3">
                        <button
                          onClick={() => handleSort("width")}
                          className="flex items-center gap-1 hover:text-white transition-colors ml-auto"
                        >
                          Width (m)
                          <ArrowUpDown className="w-3 h-3" />
                        </button>
                      </th>
                      <th className="text-left text-xs font-medium text-[#64748B] uppercase tracking-wider px-4 py-3">
                        <button
                          onClick={() => handleSort("fire_rating")}
                          className="flex items-center gap-1 hover:text-white transition-colors"
                        >
                          Fire Rating
                          <ArrowUpDown className="w-3 h-3" />
                        </button>
                      </th>
                      <th className="text-right text-xs font-medium text-[#64748B] uppercase tracking-wider px-4 py-3">
                        <button
                          onClick={() => handleSort("confidence")}
                          className="flex items-center gap-1 hover:text-white transition-colors ml-auto"
                        >
                          Confidence
                          <ArrowUpDown className="w-3 h-3" />
                        </button>
                      </th>
                      <th className="text-center text-xs font-medium text-[#64748B] uppercase tracking-wider px-4 py-3">
                        Page
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {sortedDoors.map((door, idx) => (
                      <tr
                        key={idx}
                        onClick={() => setSelectedDoor(door)}
                        className={`hover:bg-white/[0.02] cursor-pointer transition-colors ${
                          selectedDoor === door ? "bg-[#00D4AA]/5" : ""
                        }`}
                      >
                        <td className="px-4 py-3 text-sm font-mono text-[#00D4AA]">
                          {door.door_number || '-'}
                        </td>
                        <td className="px-4 py-3 text-sm text-white">
                          {door.section}
                        </td>
                        <td className="px-4 py-3 text-sm text-white text-right font-mono">
                          {door.width_m?.toFixed(2) || '-'}
                        </td>
                        <td className="px-4 py-3 text-sm text-white">
                          {door.fire_rating || '-'}
                        </td>
                        <td className="px-4 py-3 text-sm text-right">
                          <span className={`${
                            door.confidence >= 0.8 ? 'text-green-400' :
                            door.confidence >= 0.6 ? 'text-yellow-400' :
                            'text-red-400'
                          }`}>
                            {(door.confidence * 100).toFixed(0)}%
                          </span>
                        </td>
                        <td className="px-4 py-3 text-sm text-[#64748B] text-center">
                          {door.page_number}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Details Panel */}
            <div className="bg-[#1A2942] rounded-xl border border-white/5 p-5">
              <h3 className="text-sm font-medium text-[#94A3B8] uppercase tracking-wider mb-4">
                Door Details
              </h3>
              {selectedDoor ? (
                <div className="space-y-4">
                  <div>
                    <p className="text-xs text-[#64748B]">Extraction ID</p>
                    <p className="text-white font-mono text-xs">
                      {selectedDoor.extraction_id}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-[#64748B]">Door Number</p>
                    <p className="text-white">{selectedDoor.door_number || 'N/A'}</p>
                  </div>
                  <div>
                    <p className="text-xs text-[#64748B]">Type</p>
                    <p className="text-white">{selectedDoor.door_type || 'Unknown'}</p>
                  </div>
                  <div>
                    <p className="text-xs text-[#64748B]">Dimensions</p>
                    <p className="text-white font-mono">
                      {selectedDoor.width_m?.toFixed(2) || '-'} × {selectedDoor.height_m?.toFixed(2) || '-'} m
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-[#64748B]">Fire Rating</p>
                    <p className="text-white">{selectedDoor.fire_rating || 'None'}</p>
                  </div>
                  <hr className="border-white/5" />
                  <div>
                    <p className="text-xs text-[#64748B]">Extraction Method</p>
                    <code className="text-xs text-[#00D4AA] font-mono">
                      {selectedDoor.extraction_method}
                    </code>
                  </div>
                  <div>
                    <p className="text-xs text-[#64748B]">Confidence</p>
                    <p className="text-white">{(selectedDoor.confidence * 100).toFixed(1)}%</p>
                  </div>
                  <div>
                    <p className="text-xs text-[#64748B]">Page</p>
                    <p className="text-white">{selectedDoor.page_number}</p>
                  </div>
                  {selectedDoor.assumptions.length > 0 && (
                    <div>
                      <p className="text-xs text-[#64748B] mb-1">Assumptions</p>
                      <ul className="text-xs text-[#94A3B8] space-y-1">
                        {selectedDoor.assumptions.map((a, i) => (
                          <li key={i}>• {a}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-sm text-[#64748B]">
                  Select a door to view details
                </p>
              )}
            </div>
          </div>
          )}

          {/* Charts View */}
          {viewMode === "charts" && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Fire Rating Distribution */}
              <div className="bg-[#1A2942] rounded-xl border border-white/5 p-6">
                <h3 className="text-lg font-semibold text-white mb-6">
                  Distribution by Fire Rating
                </h3>
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie
                      data={fireRatingData}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, value, percent }) =>
                        `${name}: ${value} (${percent ? (percent * 100).toFixed(0) : 0}%)`
                      }
                      outerRadius={100}
                      fill="#8884d8"
                      dataKey="value"
                    >
                      {fireRatingData.map((entry, index) => (
                        <Cell
                          key={`cell-${index}`}
                          fill={FIRE_RATING_COLORS[entry.name] || "#64748B"}
                        />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#1A2942",
                        border: "1px solid rgba(255,255,255,0.1)",
                        borderRadius: "8px",
                        color: "#fff"
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>

                {/* Legend */}
                <div className="mt-6 grid grid-cols-2 gap-3">
                  {fireRatingData.map((entry) => (
                    <div key={entry.name} className="flex items-center gap-2">
                      <div
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: FIRE_RATING_COLORS[entry.name] || "#64748B" }}
                      />
                      <span className="text-sm text-[#94A3B8]">
                        {entry.name}: <span className="text-white font-medium">{entry.value}</span>
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Section Distribution */}
              <div className="bg-[#1A2942] rounded-xl border border-white/5 p-6">
                <h3 className="text-lg font-semibold text-white mb-6">
                  Distribution by Section
                </h3>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={sectionData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                    <XAxis
                      dataKey="name"
                      stroke="#94A3B8"
                      style={{ fontSize: '12px' }}
                    />
                    <YAxis
                      stroke="#94A3B8"
                      style={{ fontSize: '12px' }}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#1A2942",
                        border: "1px solid rgba(255,255,255,0.1)",
                        borderRadius: "8px",
                        color: "#fff"
                      }}
                      labelStyle={{ color: "#fff" }}
                    />
                    <Bar dataKey="count" fill="#00D4AA" radius={[8, 8, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>

                {/* Summary */}
                <div className="mt-6 grid grid-cols-2 gap-3">
                  {sectionData.map((entry) => (
                    <div key={entry.name} className="bg-[#0F1B2A] rounded-lg p-3">
                      <p className="text-xs text-[#64748B]">{entry.name}</p>
                      <p className="text-xl font-bold text-white mt-1">{entry.count} doors</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Summary Statistics */}
              <div className="lg:col-span-2 bg-[#1A2942] rounded-xl border border-white/5 p-6">
                <h3 className="text-lg font-semibold text-white mb-4">Summary Statistics</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-[#0F1B2A] rounded-lg p-4">
                    <p className="text-sm text-[#64748B]">Total Doors</p>
                    <p className="text-2xl font-bold text-white mt-1">{result.total_doors}</p>
                  </div>
                  <div className="bg-[#0F1B2A] rounded-lg p-4">
                    <p className="text-sm text-[#64748B]">Fire-Rated</p>
                    <p className="text-2xl font-bold text-[#00D4AA] mt-1">
                      {fireRatingData.filter(d => d.name !== "Standard").reduce((sum, d) => sum + d.value, 0)}
                    </p>
                  </div>
                  <div className="bg-[#0F1B2A] rounded-lg p-4">
                    <p className="text-sm text-[#64748B]">Avg Width</p>
                    <p className="text-2xl font-bold text-white mt-1">
                      {result.summary.avg_width_m?.toFixed(2) || '-'}<span className="text-sm text-[#94A3B8] ml-1">m</span>
                    </p>
                  </div>
                  <div className="bg-[#0F1B2A] rounded-lg p-4">
                    <p className="text-sm text-[#64748B]">Sections</p>
                    <p className="text-2xl font-bold text-white mt-1">{sectionData.length}</p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Summary by Type */}
          {Object.keys(result.summary.by_type).length > 0 && (
            <div className="bg-[#1A2942] rounded-xl border border-white/5 p-6">
              <h3 className="text-lg font-semibold text-white mb-4">Doors by Type</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {Object.entries(result.summary.by_type).map(([type, count]) => (
                  <div key={type} className="bg-[#0F1B2A] rounded-lg p-4">
                    <p className="text-sm text-[#64748B]">{type}</p>
                    <p className="text-2xl font-bold text-white mt-1">{count}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
