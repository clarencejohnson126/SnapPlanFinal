import Link from "next/link";
import { createClient } from "@/lib/supabase/server";

// Project card component
function ProjectCard({
  id,
  name,
  description,
  fileCount,
  jobCount,
  lastUpdated,
}: {
  id: string;
  name: string;
  description?: string;
  fileCount: number;
  jobCount: number;
  lastUpdated: string;
}) {
  return (
    <Link
      href={`/app/projects/${id}`}
      className="group bg-[#1A2942] rounded-xl border border-white/5 overflow-hidden hover:border-[#00D4AA]/30 transition-colors"
    >
      {/* Blueprint preview placeholder */}
      <div className="h-40 bg-[#0F1B2A] relative overflow-hidden">
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
            className="w-16 h-16 text-[#00D4AA]/20"
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
      <div className="p-5">
        <h3 className="font-semibold text-white text-lg group-hover:text-[#00D4AA] transition-colors">
          {name}
        </h3>
        {description && (
          <p className="text-[#64748B] text-sm mt-1 line-clamp-2">
            {description}
          </p>
        )}
        <div className="flex items-center gap-4 mt-4 text-sm text-[#94A3B8]">
          <span className="flex items-center gap-1.5">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            {fileCount} {fileCount === 1 ? "file" : "files"}
          </span>
          <span className="flex items-center gap-1.5">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
            {jobCount} {jobCount === 1 ? "analysis" : "analyses"}
          </span>
        </div>
        <p className="text-[#64748B] text-xs mt-3">{lastUpdated}</p>
      </div>
    </Link>
  );
}

// New project card
function NewProjectCard() {
  return (
    <Link
      href="/app/projects/new"
      className="group bg-[#1A2942]/50 rounded-xl border border-dashed border-white/10 hover:border-[#00D4AA]/50 transition-colors flex flex-col items-center justify-center min-h-[280px]"
    >
      <div className="w-14 h-14 rounded-full bg-[#00D4AA]/10 flex items-center justify-center group-hover:bg-[#00D4AA]/20 transition-colors">
        <svg
          className="w-7 h-7 text-[#00D4AA]"
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
      <p className="text-[#94A3B8] mt-4 font-medium group-hover:text-white transition-colors">
        Create New Project
      </p>
      <p className="text-[#64748B] text-sm mt-1">
        Start analyzing floor plans
      </p>
    </Link>
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

export default async function ProjectsPage() {
  const supabase = await createClient();

  // Get current user
  const {
    data: { user },
  } = await supabase.auth.getUser();

  // Fetch all projects with counts
  let projects: Array<{
    id: string;
    name: string;
    description?: string;
    created_at: string;
    file_count: number;
    job_count: number;
  }> = [];

  try {
    if (!user?.id) {
      return (
        <div className="space-y-6">
          <div className="text-center text-[#94A3B8] py-8">
            Please sign in to view your projects.
          </div>
        </div>
      );
    }

    const { data } = await supabase
      .from("projects")
      .select("id, name, description, created_at")
      .eq("user_id", user.id)
      .order("created_at", { ascending: false }) as { data: { id: string; name: string; description?: string; created_at: string }[] | null };

    if (data) {
      projects = await Promise.all(
        data.map(async (project) => {
          // Get file count
          const { count: fileCount } = await supabase
            .from("files")
            .select("*", { count: "exact", head: true })
            .eq("project_id", project.id);

          // Get job count
          const { count: jobCount } = await supabase
            .from("jobs")
            .select("*", { count: "exact", head: true })
            .eq("project_id", project.id);

          return {
            ...project,
            file_count: fileCount || 0,
            job_count: jobCount || 0,
          };
        })
      );
    }
  } catch {
    // Table might not exist yet
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Projects</h1>
          <p className="text-[#94A3B8] mt-1">
            Manage your construction document projects
          </p>
        </div>
        <Link
          href="/app/projects/new"
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-[#00D4AA] text-[#0F1B2A] font-semibold hover:bg-[#00D4AA]/90 transition-colors"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Project
        </Link>
      </div>

      {/* Projects grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {projects.map((project) => (
          <ProjectCard
            key={project.id}
            id={project.id}
            name={project.name}
            description={project.description}
            fileCount={project.file_count}
            jobCount={project.job_count}
            lastUpdated={formatRelativeTime(new Date(project.created_at))}
          />
        ))}
        <NewProjectCard />
      </div>

      {/* Empty state */}
      {projects.length === 0 && (
        <div className="text-center py-12">
          <svg
            className="w-16 h-16 text-[#64748B] mx-auto mb-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1}
              d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
            />
          </svg>
          <h3 className="text-lg font-medium text-white">No projects yet</h3>
          <p className="text-[#94A3B8] mt-1">
            Create your first project to start analyzing floor plans
          </p>
        </div>
      )}
    </div>
  );
}
