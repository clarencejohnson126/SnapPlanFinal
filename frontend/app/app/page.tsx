"use client";

import Link from "next/link";
import { useLanguage } from "@/lib/i18n";

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

export default function DashboardPage() {
  const { t } = useLanguage();

  return (
    <div className="space-y-8">
      {/* Welcome header */}
      <div>
        <h1 className="text-2xl font-bold text-white">
          {t.dashboard.welcome}
        </h1>
        <p className="text-[#94A3B8] mt-1">
          {t.dashboard.subtitle}
        </p>
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Link
          href="/app/scan"
          className="group bg-gradient-to-br from-[#00D4AA]/10 to-[#00D4AA]/5 rounded-xl border border-[#00D4AA]/20 hover:border-[#00D4AA]/40 p-8 transition-all"
        >
          <div className="w-16 h-16 rounded-2xl bg-[#00D4AA]/20 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
            <svg
              className="w-8 h-8 text-[#00D4AA]"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
          </div>
          <h2 className="text-xl font-semibold text-white mb-2">{t.dashboard.quickScan}</h2>
          <p className="text-[#94A3B8]">
            {t.dashboard.quickScanDesc}
          </p>
          <div className="mt-4 inline-flex items-center gap-2 text-[#00D4AA] font-medium">
            {t.dashboard.startScanning}
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
            </svg>
          </div>
        </Link>

        <div className="bg-[#1A2942] rounded-xl border border-white/5 p-8">
          <div className="w-16 h-16 rounded-2xl bg-[#3B82F6]/20 flex items-center justify-center mb-6">
            <svg
              className="w-8 h-8 text-[#3B82F6]"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
              />
            </svg>
          </div>
          <h2 className="text-xl font-semibold text-white mb-2">{t.dashboard.howItWorks}</h2>
          <ol className="text-[#94A3B8] space-y-2 list-decimal list-inside">
            <li>{t.dashboard.step1}</li>
            <li>{t.dashboard.step2}</li>
            <li>{t.dashboard.step3}</li>
            <li>{t.dashboard.step4}</li>
          </ol>
        </div>
      </div>

      {/* Features */}
      <div>
        <h2 className="text-lg font-semibold text-white mb-4">{t.dashboard.extractionPattern}</h2>
        <div className="bg-[#1A2942] rounded-xl border border-white/5 p-5 max-w-md">
          <code className="text-[#00D4AA] font-mono text-lg">NGF:</code>
          <p className="text-[#94A3B8] text-sm mt-2">{t.dashboard.ngfDesc}</p>
        </div>
      </div>

      {/* Info cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <StatCard label={t.dashboard.extractionMethod} value={t.dashboard.textBased} subtitle={t.dashboard.deterministic} />
        <StatCard label={t.dashboard.exportFormats} value="3" subtitle={t.dashboard.exportFormatsDesc} />
      </div>
    </div>
  );
}
