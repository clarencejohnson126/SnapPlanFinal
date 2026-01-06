"use client";

import { useState, useCallback, use } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { UploadDropzone, PdfPreview } from "@/components/upload";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function UploadPage({ params }: PageProps) {
  const { id: projectId } = use(params);
  const router = useRouter();
  const supabase = createClient();

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Configuration
  const [balconyFactor, setBalconyFactor] = useState("0.5");

  const handleFileSelect = useCallback((file: File) => {
    setSelectedFile(file);
    setError(null);
  }, []);

  const handleRemoveFile = useCallback(() => {
    setSelectedFile(null);
  }, []);

  const handleStartAnalysis = async () => {
    if (!selectedFile) return;

    setIsUploading(true);
    setError(null);

    try {
      // Get current user
      const {
        data: { user },
      } = await supabase.auth.getUser();

      if (!user) {
        setError("You must be logged in");
        setIsUploading(false);
        return;
      }

      // 1. Upload file to Supabase Storage
      const fileId = crypto.randomUUID();
      const filePath = `${user.id}/${projectId}/${fileId}/${selectedFile.name}`;

      const { error: uploadError } = await supabase.storage
        .from("snapplan-files")
        .upload(filePath, selectedFile, {
          contentType: "application/pdf",
          upsert: false,
        });

      if (uploadError) {
        throw new Error(`Upload failed: ${uploadError.message}`);
      }

      // 2. Create file record in database
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { data: fileRecord, error: fileError } = await (supabase as any)
        .from("files")
        .insert({
          id: fileId,
          project_id: projectId,
          user_id: user.id,
          name: selectedFile.name,
          storage_path: filePath,
          mime_type: "application/pdf",
          size_bytes: selectedFile.size,
        })
        .select("id")
        .single() as { data: { id: string } | null; error: unknown };

      if (fileError) {
        throw new Error(`File record creation failed: ${String(fileError)}`);
      }

      setIsUploading(false);
      setIsProcessing(true);

      // 3. Create job
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { data: job, error: jobError } = await (supabase as any)
        .from("jobs")
        .insert({
          user_id: user.id,
          project_id: projectId,
          file_id: fileRecord?.id,
          job_type: "area_text",
          status: "queued",
          config: {
            balcony_factor: parseFloat(balconyFactor),
          },
        })
        .select("id")
        .single() as { data: { id: string } | null; error: unknown };

      if (jobError || !job) {
        throw new Error(`Job creation failed: ${jobError ? String(jobError) : "Unknown error"}`);
      }

      // 4. Trigger processing via Edge Function (or API route)
      // For now, we'll poll the job status
      // In production, this would call the Edge Function

      // Redirect to results page (will show processing status)
      router.push(`/app/projects/${projectId}/results/${job.id}`);
    } catch (err) {
      console.error("Error:", err);
      setError(err instanceof Error ? err.message : "An error occurred");
      setIsUploading(false);
      setIsProcessing(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto">
      {/* Breadcrumb */}
      <nav className="mb-6">
        <ol className="flex items-center gap-2 text-sm">
          <li>
            <Link href="/app/projects" className="text-[#94A3B8] hover:text-white">
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
          <li className="text-white">Upload</li>
        </ol>
      </nav>

      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white">Upload Floor Plan</h1>
          <p className="text-[#94A3B8] mt-1">
            Upload a PDF to extract room areas automatically
          </p>
        </div>
        <div className="text-sm text-[#64748B]">Step 1 of 2</div>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-6 p-4 rounded-lg bg-red-500/10 border border-red-500/20">
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      {/* Main content */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Left: Upload / Preview */}
        <div>
          {selectedFile ? (
            <PdfPreview file={selectedFile} onRemove={handleRemoveFile} />
          ) : (
            <UploadDropzone
              onFileSelect={handleFileSelect}
              isUploading={isUploading}
            />
          )}
        </div>

        {/* Right: Configuration */}
        <div className="bg-[#1A2942] rounded-xl border border-white/5 p-6">
          <h2 className="text-lg font-semibold text-white mb-6">Configuration</h2>

          <div className="space-y-6">
            {/* Document type */}
            <div>
              <label className="block text-sm font-medium text-[#94A3B8] mb-2">
                Document Type
              </label>
              <select
                className="w-full px-4 py-3 rounded-lg bg-[#0F1B2A] border border-white/10 text-white focus:outline-none focus:ring-2 focus:ring-[#00D4AA]/50 focus:border-[#00D4AA] transition-colors"
                defaultValue="floor_plan"
              >
                <option value="floor_plan">Floor Plan (Grundriss)</option>
              </select>
              <p className="text-xs text-[#64748B] mt-1">
                Only floor plans with NRF values are supported in MVP
              </p>
            </div>

            {/* Analysis type */}
            <div>
              <label className="block text-sm font-medium text-[#94A3B8] mb-2">
                Analysis Type
              </label>
              <select
                className="w-full px-4 py-3 rounded-lg bg-[#0F1B2A] border border-white/10 text-white focus:outline-none focus:ring-2 focus:ring-[#00D4AA]/50 focus:border-[#00D4AA] transition-colors"
                defaultValue="area_text"
              >
                <option value="area_text">Area Extraction (Text)</option>
                <option value="doors" disabled>
                  Door Schedule (Coming Soon)
                </option>
                <option value="windows" disabled>
                  Windows (Coming Soon)
                </option>
              </select>
            </div>

            {/* Balcony factor */}
            <div>
              <label className="block text-sm font-medium text-[#94A3B8] mb-2">
                Balcony Factor
              </label>
              <select
                value={balconyFactor}
                onChange={(e) => setBalconyFactor(e.target.value)}
                className="w-full px-4 py-3 rounded-lg bg-[#0F1B2A] border border-white/10 text-white focus:outline-none focus:ring-2 focus:ring-[#00D4AA]/50 focus:border-[#00D4AA] transition-colors"
              >
                <option value="0.25">0.25 (25%)</option>
                <option value="0.5">0.5 (50%) - Standard</option>
                <option value="0.75">0.75 (75%)</option>
                <option value="1.0">1.0 (100%)</option>
              </select>
              <p className="text-xs text-[#64748B] mt-1">
                Factor applied to Balkon, Terrasse, and Loggia areas
              </p>
            </div>

            {/* Divider */}
            <hr className="border-white/5" />

            {/* Start button */}
            <button
              onClick={handleStartAnalysis}
              disabled={!selectedFile || isUploading || isProcessing}
              className="w-full py-3 px-4 rounded-lg bg-[#00D4AA] text-[#0F1B2A] font-semibold hover:bg-[#00D4AA]/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
            >
              {isUploading ? (
                <>
                  <svg
                    className="w-5 h-5 animate-spin"
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
                  Uploading...
                </>
              ) : isProcessing ? (
                <>
                  <svg
                    className="w-5 h-5 animate-spin"
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
                  Starting Analysis...
                </>
              ) : (
                <>
                  Start Analysis
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
                      d="M14 5l7 7m0 0l-7 7m7-7H3"
                    />
                  </svg>
                </>
              )}
            </button>

            {!selectedFile && (
              <p className="text-xs text-center text-[#64748B]">
                Select a PDF file to continue
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
