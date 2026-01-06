import Link from "next/link";
import { createClient } from "@/lib/supabase/server";

// Stats card component
function StatCard({
  label,
  value,
  subtitle,
}: {
  label: string;
  value: string | number;
  subtitle?: string;
}) {
  return (
    <div className="bg-[#1A2942] rounded-xl p-6 border border-white/5">
      <p className="text-[#94A3B8] text-sm font-medium">{label}</p>
      <p className="text-3xl font-bold text-white mt-2 font-mono">{value}</p>
      {subtitle && <p className="text-[#64748B] text-xs mt-1">{subtitle}</p>}
    </div>
  );
}

// Project card component
function ProjectCard({
  id,
  name,
  fileCount,
  lastUpdated,
}: {
  id: string;
  name: string;
  fileCount: number;
  lastUpdated: string;
}) {
  return (
    <Link
      href={`/app/projects/${id}`}
      className="group bg-[#1A2942] rounded-xl border border-white/5 overflow-hidden hover:border-[#00D4AA]/30 transition-colors"
    >
      {/* Blueprint preview placeholder */}
      <div className="h-32 bg-[#0F1B2A] relative overflow-hidden">
        <div
          className="absolute inset-0 opacity-10"
          style={{
            backgroundImage: `
              linear-gradient(rgba(0, 212, 170, 0.5) 1px, transparent 1px),
              linear-gradient(90deg, rgba(0, 212, 170, 0.5) 1px, transparent 1px)
            `,
            backgroundSize: "20px 20px",
          }}
        />
        <div className="absolute inset-0 flex items-center justify-center">
          <svg
            className="w-12 h-12 text-[#00D4AA]/20"
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
        </div>
      </div>
      <div className="p-4">
        <h3 className="font-semibold text-white group-hover:text-[#00D4AA] transition-colors">
          {name}
        </h3>
        <p className="text-[#64748B] text-sm mt-1">
          {fileCount} {fileCount === 1 ? "file" : "files"}
        </p>
        <p className="text-[#64748B] text-xs mt-2">{lastUpdated}</p>
      </div>
    </Link>
  );
}

// New project card
function NewProjectCard() {
  return (
    <Link
      href="/app/projects/new"
      className="group bg-[#1A2942]/50 rounded-xl border border-dashed border-white/10 hover:border-[#00D4AA]/50 transition-colors flex flex-col items-center justify-center min-h-[200px]"
    >
      <div className="w-12 h-12 rounded-full bg-[#00D4AA]/10 flex items-center justify-center group-hover:bg-[#00D4AA]/20 transition-colors">
        <svg
          className="w-6 h-6 text-[#00D4AA]"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 4v16m8-8H4"
          />
        </svg>
      </div>
      <p className="text-[#94A3B8] mt-3 font-medium group-hover:text-white transition-colors">
        New Project
      </p>
    </Link>
  );
}

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

export default async function DashboardPage() {
  const supabase = await createClient();

  // Get current user
  const {
    data: { user },
  } = await supabase.auth.getUser();

  // Fetch stats (with error handling for missing tables)
  let projectCount = 0;
  let totalArea = 0;
  let jobCount = 0;
  let monthlyJobs = 0;

  try {
    if (user?.id) {
      const { count } = await supabase
        .from("projects")
        .select("*", { count: "exact", head: true })
        .eq("user_id", user.id);
      projectCount = count || 0;
    }
  } catch {
    // Table might not exist yet
  }

  try {
    const { data: totals } = await supabase
      .from("job_totals")
      .select("total_area_m2, job_id") as { data: { total_area_m2: number; job_id: string }[] | null };
    totalArea =
      totals?.reduce((sum, t) => sum + (t.total_area_m2 || 0), 0) || 0;
  } catch {
    // Table might not exist yet
  }

  try {
    if (user?.id) {
      const { count } = await supabase
        .from("jobs")
        .select("*", { count: "exact", head: true })
        .eq("user_id", user.id);
      jobCount = count || 0;
    }
  } catch {
    // Table might not exist yet
  }

  try {
    if (user?.id) {
      const thirtyDaysAgo = new Date();
      thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

      const { count } = await supabase
        .from("jobs")
        .select("*", { count: "exact", head: true })
        .eq("user_id", user.id)
        .gte("created_at", thirtyDaysAgo.toISOString());
      monthlyJobs = count || 0;
    }
  } catch {
    // Table might not exist yet
  }

  // Fetch recent projects
  let recentProjects: Array<{
    id: string;
    name: string;
    created_at: string;
    file_count: number;
  }> = [];

  try {
    if (user?.id) {
      const { data } = await supabase
        .from("projects")
        .select("id, name, created_at")
        .eq("user_id", user.id)
        .order("created_at", { ascending: false })
        .limit(5) as { data: { id: string; name: string; created_at: string }[] | null };

      if (data) {
        // Get file counts for each project
        recentProjects = await Promise.all(
          data.map(async (project) => {
            const { count } = await supabase
              .from("files")
              .select("*", { count: "exact", head: true })
              .eq("project_id", project.id);

            return {
              ...project,
              file_count: count || 0,
            };
          })
        );
      }
    }
  } catch {
    // Table might not exist yet
  }

  // Fetch recent jobs
  let recentJobs: Array<{
    id: string;
    status: string;
    created_at: string;
    project_name: string;
    file_name: string;
  }> = [];

  try {
    if (user?.id) {
      type JobWithRelations = {
        id: string;
        status: string;
        created_at: string;
        projects: { name: string } | null;
        files: { name: string } | null;
      };

      const { data } = await supabase
        .from("jobs")
        .select(
          `
          id,
          status,
          created_at,
          projects(name),
          files(name)
        `
        )
        .eq("user_id", user.id)
        .order("created_at", { ascending: false })
        .limit(5) as { data: JobWithRelations[] | null };

      if (data) {
        recentJobs = data.map((job) => ({
          id: job.id,
          status: job.status,
          created_at: job.created_at,
          project_name: job.projects?.name || "Unknown",
          file_name: job.files?.name || "Unknown",
        }));
      }
    }
  } catch {
    // Table might not exist yet
  }

  const userName = user?.email?.split("@")[0] || "User";

  return (
    <div className="space-y-8">
      {/* Welcome header */}
      <div>
        <h1 className="text-2xl font-bold text-white">
          Welcome back, {userName}
        </h1>
        <p className="text-[#94A3B8] mt-1">
          Here&apos;s an overview of your construction document analysis
        </p>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Projects" value={projectCount} />
        <StatCard
          label="Total Area"
          value={totalArea.toLocaleString("de-DE", { maximumFractionDigits: 0 })}
          subtitle="m²"
        />
        <StatCard label="Analyses" value={jobCount} />
        <StatCard label="This Month" value={monthlyJobs} subtitle="analyses" />
      </div>

      {/* Recent projects */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">Recent Projects</h2>
          <Link
            href="/app/projects"
            className="text-sm text-[#00D4AA] hover:underline"
          >
            View all
          </Link>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {recentProjects.map((project) => (
            <ProjectCard
              key={project.id}
              id={project.id}
              name={project.name}
              fileCount={project.file_count}
              lastUpdated={formatRelativeTime(new Date(project.created_at))}
            />
          ))}
          <NewProjectCard />
        </div>
      </div>

      {/* Recent runs table */}
      <div>
        <h2 className="text-lg font-semibold text-white mb-4">Recent Analyses</h2>
        <div className="bg-[#1A2942] rounded-xl border border-white/5 overflow-hidden">
          {recentJobs.length > 0 ? (
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/5">
                  <th className="text-left text-xs font-medium text-[#64748B] uppercase tracking-wider px-6 py-4">
                    Project
                  </th>
                  <th className="text-left text-xs font-medium text-[#64748B] uppercase tracking-wider px-6 py-4">
                    File
                  </th>
                  <th className="text-left text-xs font-medium text-[#64748B] uppercase tracking-wider px-6 py-4">
                    Status
                  </th>
                  <th className="text-left text-xs font-medium text-[#64748B] uppercase tracking-wider px-6 py-4">
                    Date
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {recentJobs.map((job) => (
                  <tr
                    key={job.id}
                    className="hover:bg-white/[0.02] transition-colors"
                  >
                    <td className="px-6 py-4 text-sm text-white">
                      {job.project_name}
                    </td>
                    <td className="px-6 py-4 text-sm text-[#94A3B8] font-mono">
                      {job.file_name}
                    </td>
                    <td className="px-6 py-4">
                      <StatusBadge status={job.status} />
                    </td>
                    <td className="px-6 py-4 text-sm text-[#64748B]">
                      {formatRelativeTime(new Date(job.created_at))}
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
                  d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
                />
              </svg>
              <p className="text-[#94A3B8]">No analyses yet</p>
              <p className="text-[#64748B] text-sm mt-1">
                Upload a floor plan to get started
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
