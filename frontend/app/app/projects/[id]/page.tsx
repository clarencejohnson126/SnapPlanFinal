import Link from "next/link";
import { notFound } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

// Job status badge
function StatusBadge({ status }: { status: string }) {
  const styles = {
    completed: "bg-[#00D4AA]/10 text-[#00D4AA]",
    processing: "bg-[#3B82F6]/10 text-[#3B82F6]",
    failed: "bg-red-500/10 text-red-400",
    queued: "bg-[#F59E0B]/10 text-[#F59E0B]",
  };

  const labels = {
    completed: "Done",
    processing: "Processing",
    failed: "Failed",
    queued: "Queued",
  };

  const style = styles[status as keyof typeof styles] || styles.queued;
  const label = labels[status as keyof typeof labels] || status;

  return (
    <span className={`px-2 py-1 rounded-full text-xs font-medium ${style}`}>
      {label}
    </span>
  );
}

// Format relative time
function formatRelativeTime(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins} min ago`;
  if (diffHours < 24) return `${diffHours} hr ago`;
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays} days ago`;
  return date.toLocaleDateString();
}

// Format file size
function formatFileSize(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function ProjectDetailPage({ params }: PageProps) {
  const { id } = await params;
  const supabase = await createClient();

  // Get current user
  const {
    data: { user },
  } = await supabase.auth.getUser();

  // Fetch project
  if (!user?.id) {
    notFound();
  }

  type Project = {
    id: string;
    name: string;
    description: string | null;
    created_at: string;
  };

  type FileRecord = {
    id: string;
    name: string;
    mime_type: string | null;
    size_bytes: number | null;
    created_at: string;
  };

  const { data: project, error: projectError } = await supabase
    .from("projects")
    .select("*")
    .eq("id", id)
    .eq("user_id", user.id)
    .single() as { data: Project | null; error: unknown };

  if (projectError || !project) {
    notFound();
  }

  // Fetch files
  const { data: files } = await supabase
    .from("files")
    .select("*")
    .eq("project_id", id)
    .order("created_at", { ascending: false }) as { data: FileRecord[] | null };

  // Fetch jobs with totals
  type JobWithRelations = {
    id: string;
    status: string;
    job_type: string | null;
    created_at: string;
    files: { name: string } | null;
    job_totals: { total_rooms: number; total_area_m2: number } | null;
  };

  const { data: jobs } = await supabase
    .from("jobs")
    .select(`
      *,
      files(name),
      job_totals(total_rooms, total_area_m2)
    `)
    .eq("project_id", id)
    .order("created_at", { ascending: false }) as { data: JobWithRelations[] | null };

  // Calculate project stats
  const totalFiles = files?.length || 0;
  const totalJobs = jobs?.length || 0;
  const completedJobs = jobs?.filter((j) => j.status === "completed").length || 0;
  const totalArea =
    jobs?.reduce((sum, j) => {
      const totals = j.job_totals as { total_area_m2?: number } | null;
      return sum + (totals?.total_area_m2 || 0);
    }, 0) || 0;

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <nav>
        <ol className="flex items-center gap-2 text-sm">
          <li>
            <Link href="/app/projects" className="text-[#94A3B8] hover:text-white">
              Projects
            </Link>
          </li>
          <li className="text-[#64748B]">/</li>
          <li className="text-white">{project.name}</li>
        </ol>
      </nav>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">{project.name}</h1>
          {project.description && (
            <p className="text-[#94A3B8] mt-1">{project.description}</p>
          )}
        </div>
        <Link
          href={`/app/projects/${id}/upload`}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-[#00D4AA] text-[#0F1B2A] font-semibold hover:bg-[#00D4AA]/90 transition-colors"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
          </svg>
          Upload Floor Plan
        </Link>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-[#1A2942] rounded-xl p-5 border border-white/5">
          <p className="text-[#94A3B8] text-sm">Files</p>
          <p className="text-2xl font-bold text-white mt-1 font-mono">{totalFiles}</p>
        </div>
        <div className="bg-[#1A2942] rounded-xl p-5 border border-white/5">
          <p className="text-[#94A3B8] text-sm">Analyses</p>
          <p className="text-2xl font-bold text-white mt-1 font-mono">{totalJobs}</p>
        </div>
        <div className="bg-[#1A2942] rounded-xl p-5 border border-white/5">
          <p className="text-[#94A3B8] text-sm">Completed</p>
          <p className="text-2xl font-bold text-[#00D4AA] mt-1 font-mono">{completedJobs}</p>
        </div>
        <div className="bg-[#1A2942] rounded-xl p-5 border border-white/5">
          <p className="text-[#94A3B8] text-sm">Total Area</p>
          <p className="text-2xl font-bold text-white mt-1 font-mono">
            {totalArea.toLocaleString("de-DE", { maximumFractionDigits: 0 })}
            <span className="text-sm text-[#94A3B8] ml-1">m²</span>
          </p>
        </div>
      </div>

      {/* Files section */}
      <div>
        <h2 className="text-lg font-semibold text-white mb-4">Files</h2>
        <div className="bg-[#1A2942] rounded-xl border border-white/5 overflow-hidden">
          {files && files.length > 0 ? (
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/5">
                  <th className="text-left text-xs font-medium text-[#64748B] uppercase tracking-wider px-6 py-4">
                    Name
                  </th>
                  <th className="text-left text-xs font-medium text-[#64748B] uppercase tracking-wider px-6 py-4">
                    Type
                  </th>
                  <th className="text-left text-xs font-medium text-[#64748B] uppercase tracking-wider px-6 py-4">
                    Size
                  </th>
                  <th className="text-left text-xs font-medium text-[#64748B] uppercase tracking-wider px-6 py-4">
                    Uploaded
                  </th>
                  <th className="text-right text-xs font-medium text-[#64748B] uppercase tracking-wider px-6 py-4">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {files.map((file) => (
                  <tr
                    key={file.id}
                    className="hover:bg-white/[0.02] transition-colors"
                  >
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <svg className="w-5 h-5 text-[#00D4AA]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                        <span className="text-sm text-white font-mono">{file.name}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm text-[#94A3B8]">
                      {file.mime_type || "PDF"}
                    </td>
                    <td className="px-6 py-4 text-sm text-[#94A3B8] font-mono">
                      {file.size_bytes ? formatFileSize(file.size_bytes) : "-"}
                    </td>
                    <td className="px-6 py-4 text-sm text-[#64748B]">
                      {formatRelativeTime(new Date(file.created_at))}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <Link
                        href={`/app/projects/${id}/upload?file=${file.id}`}
                        className="text-sm text-[#00D4AA] hover:underline"
                      >
                        Analyze
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="px-6 py-12 text-center">
              <svg
                className="w-12 h-12 text-[#64748B] mx-auto mb-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1}
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                />
              </svg>
              <p className="text-[#94A3B8]">No files uploaded yet</p>
              <Link
                href={`/app/projects/${id}/upload`}
                className="inline-flex items-center gap-2 mt-4 text-sm text-[#00D4AA] hover:underline"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                </svg>
                Upload your first floor plan
              </Link>
            </div>
          )}
        </div>
      </div>

      {/* Analyses section */}
      <div>
        <h2 className="text-lg font-semibold text-white mb-4">Analyses</h2>
        <div className="bg-[#1A2942] rounded-xl border border-white/5 overflow-hidden">
          {jobs && jobs.length > 0 ? (
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/5">
                  <th className="text-left text-xs font-medium text-[#64748B] uppercase tracking-wider px-6 py-4">
                    File
                  </th>
                  <th className="text-left text-xs font-medium text-[#64748B] uppercase tracking-wider px-6 py-4">
                    Type
                  </th>
                  <th className="text-left text-xs font-medium text-[#64748B] uppercase tracking-wider px-6 py-4">
                    Status
                  </th>
                  <th className="text-left text-xs font-medium text-[#64748B] uppercase tracking-wider px-6 py-4">
                    Rooms
                  </th>
                  <th className="text-left text-xs font-medium text-[#64748B] uppercase tracking-wider px-6 py-4">
                    Area
                  </th>
                  <th className="text-left text-xs font-medium text-[#64748B] uppercase tracking-wider px-6 py-4">
                    Date
                  </th>
                  <th className="text-right text-xs font-medium text-[#64748B] uppercase tracking-wider px-6 py-4">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {jobs.map((job) => {
                  const totals = job.job_totals;
                  const fileName = job.files?.name || "Unknown";
                  return (
                    <tr
                      key={job.id}
                      className="hover:bg-white/[0.02] transition-colors"
                    >
                      <td className="px-6 py-4 text-sm text-white font-mono">
                        {fileName}
                      </td>
                      <td className="px-6 py-4 text-sm text-[#94A3B8] capitalize">
                        {job.job_type?.replace("_", " ") || "Area"}
                      </td>
                      <td className="px-6 py-4">
                        <StatusBadge status={job.status} />
                      </td>
                      <td className="px-6 py-4 text-sm text-white font-mono">
                        {totals?.total_rooms || "-"}
                      </td>
                      <td className="px-6 py-4 text-sm text-white font-mono">
                        {totals?.total_area_m2
                          ? `${totals.total_area_m2.toLocaleString("de-DE", { maximumFractionDigits: 2 })} m²`
                          : "-"}
                      </td>
                      <td className="px-6 py-4 text-sm text-[#64748B]">
                        {formatRelativeTime(new Date(job.created_at))}
                      </td>
                      <td className="px-6 py-4 text-right">
                        {job.status === "completed" ? (
                          <Link
                            href={`/app/projects/${id}/results/${job.id}`}
                            className="text-sm text-[#00D4AA] hover:underline"
                          >
                            View Results
                          </Link>
                        ) : job.status === "processing" ? (
                          <Link
                            href={`/app/projects/${id}/runs/${job.id}`}
                            className="text-sm text-[#3B82F6] hover:underline"
                          >
                            View Progress
                          </Link>
                        ) : job.status === "failed" ? (
                          <span className="text-sm text-red-400">Failed</span>
                        ) : (
                          <span className="text-sm text-[#64748B]">Queued</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <div className="px-6 py-12 text-center">
              <svg
                className="w-12 h-12 text-[#64748B] mx-auto mb-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1}
                  d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
                />
              </svg>
              <p className="text-[#94A3B8]">No analyses yet</p>
              <p className="text-[#64748B] text-sm mt-1">
                Upload a floor plan to start analyzing
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
