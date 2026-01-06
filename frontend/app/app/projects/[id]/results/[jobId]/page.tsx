"use client";

import { useState, useEffect, useCallback, use } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import {
  AreasTable,
  TotalsCard,
  AuditPanel,
  ResultsTabs,
  ExportModal,
} from "@/components/results";
import type { AreaResult } from "@/components/results";

interface PageProps {
  params: Promise<{ id: string; jobId: string }>;
}

// Job status component
function JobStatus({
  status,
  errorMessage,
}: {
  status: string;
  errorMessage?: string;
}) {
  if (status === "completed") return null;

  const statusConfig = {
    queued: {
      title: "Queued",
      description: "Your analysis is waiting to be processed...",
      color: "text-[#F59E0B]",
      bgColor: "bg-[#F59E0B]/10",
    },
    processing: {
      title: "Processing",
      description: "Extracting room areas from your floor plan...",
      color: "text-[#3B82F6]",
      bgColor: "bg-[#3B82F6]/10",
    },
    failed: {
      title: "Failed",
      description: errorMessage || "An error occurred during processing",
      color: "text-red-400",
      bgColor: "bg-red-500/10",
    },
  };

  const config = statusConfig[status as keyof typeof statusConfig] || statusConfig.queued;

  return (
    <div className={`${config.bgColor} rounded-xl border border-white/5 p-8 text-center`}>
      {status !== "failed" && (
        <svg
          className={`w-12 h-12 ${config.color} mx-auto mb-4 animate-spin`}
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          />
        </svg>
      )}
      {status === "failed" && (
        <svg
          className="w-12 h-12 text-red-400 mx-auto mb-4"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      )}
      <h3 className={`text-lg font-semibold ${config.color}`}>{config.title}</h3>
      <p className="text-[#94A3B8] mt-2">{config.description}</p>
    </div>
  );
}

export default function ResultsPage({ params }: PageProps) {
  const { id: projectId, jobId } = use(params);
  const supabase = createClient();

  const [job, setJob] = useState<{
    id: string;
    status: string;
    error_message?: string;
    config: Record<string, unknown>;
    files: { name: string } | null;
  } | null>(null);
  const [areas, setAreas] = useState<AreaResult[]>([]);
  const [totals, setTotals] = useState<{
    total_rooms: number;
    total_area_m2: number;
    total_effective_area_m2: number;
  } | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedArea, setSelectedArea] = useState<AreaResult | null>(null);
  const [isAuditPanelOpen, setIsAuditPanelOpen] = useState(false);
  const [isExportModalOpen, setIsExportModalOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("areas");

  // Fetch job data
  type JobData = {
    id: string;
    status: string;
    error_message?: string;
    config: Record<string, unknown>;
    files: { name: string } | null;
  };

  const fetchData = useCallback(async () => {
    try {
      // Fetch job
      const { data: jobData, error: jobError } = await supabase
        .from("jobs")
        .select("*, files(name)")
        .eq("id", jobId)
        .single() as { data: JobData | null; error: unknown };

      if (jobError) throw jobError;
      setJob(jobData);

      // If completed, fetch results
      if (jobData?.status === "completed") {
        // Fetch areas
        const { data: areasData } = await supabase
          .from("area_results")
          .select("*")
          .eq("job_id", jobId)
          .order("source_page", { ascending: true });

        if (areasData) {
          setAreas(areasData as AreaResult[]);
        }

        // Fetch totals
        const { data: totalsData } = await supabase
          .from("job_totals")
          .select("*")
          .eq("job_id", jobId)
          .single();

        if (totalsData) {
          setTotals(totalsData);
        }
      }
    } catch (err) {
      console.error("Error fetching data:", err);
    } finally {
      setIsLoading(false);
    }
  }, [supabase, jobId]);

  useEffect(() => {
    fetchData();

    // Poll for status updates if not completed
    const interval = setInterval(() => {
      if (job?.status === "queued" || job?.status === "processing") {
        fetchData();
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [fetchData, job?.status]);

  // Handle row selection
  const handleSelectArea = (area: AreaResult) => {
    setSelectedArea(area);
    setIsAuditPanelOpen(true);
  };

  // Handle export
  const handleExport = async (format: string) => {
    if (format === "json") {
      const exportData = {
        job: {
          id: job?.id,
          status: job?.status,
          config: job?.config,
        },
        totals,
        areas: areas.map((a) => ({
          room_id: a.room_id,
          room_name: a.room_name,
          room_type: a.room_type,
          area_m2: a.area_m2,
          area_factor: a.area_factor,
          effective_area_m2: a.effective_area_m2,
          source_text: a.source_text,
          source_page: a.source_page,
          source_bbox: a.source_bbox,
          confidence: a.confidence,
        })),
      };

      const blob = new Blob([JSON.stringify(exportData, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `snapplan-results-${jobId}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }

    setIsExportModalOpen(false);
  };

  const balconyFactor =
    (job?.config as { balcony_factor?: number })?.balcony_factor ?? 0.5;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <svg
          className="w-8 h-8 text-[#00D4AA] animate-spin"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          />
        </svg>
      </div>
    );
  }

  return (
    <div className="flex gap-6">
      {/* Main content */}
      <div className="flex-1 space-y-6">
        {/* Breadcrumb */}
        <nav>
          <ol className="flex items-center gap-2 text-sm">
            <li>
              <Link
                href="/app/projects"
                className="text-[#94A3B8] hover:text-white"
              >
                Projects
              </Link>
            </li>
            <li className="text-[#64748B]">/</li>
            <li>
              <Link
                href={`/app/projects/${projectId}`}
                className="text-[#94A3B8] hover:text-white"
              >
                Project
              </Link>
            </li>
            <li className="text-[#64748B]">/</li>
            <li className="text-white">Results</li>
          </ol>
        </nav>

        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">
              Results: {(job?.files as { name: string } | null)?.name || "Analysis"}
            </h1>
            <p className="text-[#94A3B8] mt-1">
              {job?.status === "completed"
                ? `${areas.length} rooms extracted`
                : `Status: ${job?.status}`}
            </p>
          </div>
          {job?.status === "completed" && (
            <button
              onClick={() => setIsExportModalOpen(true)}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-[#1A2942] border border-white/10 text-white hover:border-white/20 transition-colors"
            >
              <svg
                className="w-5 h-5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                />
              </svg>
              Export
            </button>
          )}
        </div>

        {/* Status indicator for non-completed jobs */}
        {job?.status !== "completed" && (
          <JobStatus status={job?.status || "queued"} errorMessage={job?.error_message} />
        )}

        {/* Results content */}
        {job?.status === "completed" && (
          <>
            {/* Tabs */}
            <ResultsTabs activeTab={activeTab} onTabChange={setActiveTab} />

            {/* Totals */}
            {totals && (
              <TotalsCard
                totalRooms={totals.total_rooms}
                totalAreaM2={totals.total_area_m2}
                effectiveAreaM2={totals.total_effective_area_m2}
                balconyFactor={balconyFactor}
              />
            )}

            {/* Areas table */}
            {activeTab === "areas" && (
              <AreasTable
                areas={areas}
                selectedId={selectedArea?.id || null}
                onSelect={handleSelectArea}
              />
            )}

            {/* Mobile audit panel toggle */}
            {selectedArea && (
              <button
                onClick={() => setIsAuditPanelOpen(true)}
                className="lg:hidden fixed bottom-6 right-6 w-14 h-14 rounded-full bg-[#00D4AA] text-[#0F1B2A] shadow-lg flex items-center justify-center"
              >
                <svg
                  className="w-6 h-6"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
              </button>
            )}
          </>
        )}
      </div>

      {/* Audit panel (desktop) */}
      {job?.status === "completed" && (
        <div className="hidden lg:block w-80 flex-shrink-0">
          <AuditPanel
            area={selectedArea}
            isOpen={true}
            onClose={() => setSelectedArea(null)}
          />
        </div>
      )}

      {/* Audit panel (mobile drawer) */}
      <AuditPanel
        area={selectedArea}
        isOpen={isAuditPanelOpen}
        onClose={() => setIsAuditPanelOpen(false)}
      />

      {/* Export modal */}
      <ExportModal
        isOpen={isExportModalOpen}
        onClose={() => setIsExportModalOpen(false)}
        onExport={handleExport}
      />
    </div>
  );
}
