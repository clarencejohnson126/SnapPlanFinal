"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";

export default function NewProjectPage() {
  const router = useRouter();
  const supabase = createClient();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);

    if (!name.trim()) {
      setError("Project name is required");
      setIsLoading(false);
      return;
    }

    try {
      // Get current user
      const {
        data: { user },
      } = await supabase.auth.getUser();

      if (!user) {
        setError("You must be logged in to create a project");
        setIsLoading(false);
        return;
      }

      // Create project
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { data, error: createError } = await (supabase as any)
        .from("projects")
        .insert({
          name: name.trim(),
          description: description.trim() || null,
          user_id: user.id,
        })
        .select("id")
        .single() as { data: { id: string } | null; error: unknown };

      if (createError || !data) {
        throw createError || new Error("Failed to create project");
      }

      // Redirect to project page
      router.push(`/app/projects/${data.id}`);
    } catch (err) {
      console.error("Error creating project:", err);
      setError("Failed to create project. Please try again.");
      setIsLoading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto">
      {/* Breadcrumb */}
      <nav className="mb-6">
        <ol className="flex items-center gap-2 text-sm">
          <li>
            <Link href="/app/projects" className="text-[#94A3B8] hover:text-white">
              Projects
            </Link>
          </li>
          <li className="text-[#64748B]">/</li>
          <li className="text-white">New Project</li>
        </ol>
      </nav>

      {/* Card */}
      <div className="bg-[#1A2942] rounded-xl border border-white/5 p-8">
        <h1 className="text-2xl font-bold text-white mb-2">Create New Project</h1>
        <p className="text-[#94A3B8] mb-8">
          A project organizes related floor plans and analyses for a building or development.
        </p>

        {/* Error */}
        {error && (
          <div className="mb-6 p-4 rounded-lg bg-red-500/10 border border-red-500/20">
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label
              htmlFor="name"
              className="block text-sm font-medium text-[#94A3B8] mb-2"
            >
              Project Name *
            </label>
            <input
              id="name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="w-full px-4 py-3 rounded-lg bg-[#0F1B2A] border border-white/10 text-white placeholder:text-[#64748B] focus:outline-none focus:ring-2 focus:ring-[#00D4AA]/50 focus:border-[#00D4AA] transition-colors"
              placeholder="e.g., Nordring Development, Haardtring Building"
            />
          </div>

          <div>
            <label
              htmlFor="description"
              className="block text-sm font-medium text-[#94A3B8] mb-2"
            >
              Description (optional)
            </label>
            <textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full px-4 py-3 rounded-lg bg-[#0F1B2A] border border-white/10 text-white placeholder:text-[#64748B] focus:outline-none focus:ring-2 focus:ring-[#00D4AA]/50 focus:border-[#00D4AA] transition-colors resize-none"
              placeholder="Brief description of the project..."
            />
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end gap-4 pt-4">
            <Link
              href="/app/projects"
              className="px-4 py-2.5 rounded-lg text-[#94A3B8] hover:text-white transition-colors"
            >
              Cancel
            </Link>
            <button
              type="submit"
              disabled={isLoading}
              className="px-6 py-2.5 rounded-lg bg-[#00D4AA] text-[#0F1B2A] font-semibold hover:bg-[#00D4AA]/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isLoading ? "Creating..." : "Create Project"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
