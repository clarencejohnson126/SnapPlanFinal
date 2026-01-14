"use client";

import Link from "next/link";
import { useLanguage } from "@/lib/i18n";
import { LanguageToggle } from "@/components/app/LanguageToggle";

export default function LandingPage() {
  const { t } = useLanguage();

  return (
    <div className="min-h-screen bg-[#0F1B2A]">
      {/* Blueprint background pattern */}
      <div
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage: `
            linear-gradient(rgba(0, 212, 170, 0.3) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0, 212, 170, 0.3) 1px, transparent 1px)
          `,
          backgroundSize: "50px 50px",
        }}
      />

      {/* Header */}
      <header className="relative z-10 border-b border-white/5">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img
              src="https://gxwzhgqeloqbgptrgcvo.supabase.co/storage/v1/object/public/all/Adobe%20Express%20-%20file.png"
              alt="SnapPlan Logo"
              className="w-10 h-10 rounded-xl"
            />
            <span className="text-xl font-bold text-white">SnapPlan</span>
          </div>
          <div className="flex items-center gap-4">
            <LanguageToggle />
            <Link
              href="/app/scan"
              className="px-4 py-2 rounded-lg bg-[#00D4AA] text-[#0F1B2A] font-semibold hover:bg-[#00D4AA]/90 transition-colors"
            >
              {t.landing.tryNow}
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <main className="relative z-10">
        <div className="max-w-7xl mx-auto px-6 py-24 text-center">
          <h1 className="text-4xl md:text-6xl font-bold text-white max-w-4xl mx-auto leading-tight">
            {t.landing.heroTitle}{" "}
            <span className="text-[#00D4AA]">{t.landing.heroHighlight}</span>
          </h1>
          <p className="text-xl text-[#94A3B8] mt-6 max-w-2xl mx-auto">
            {t.landing.heroDescription}
          </p>
          <div className="flex items-center justify-center gap-4 mt-10">
            <Link
              href="/app/scan"
              className="px-6 py-3 rounded-lg bg-[#00D4AA] text-[#0F1B2A] font-semibold hover:bg-[#00D4AA]/90 transition-colors"
            >
              {t.landing.uploadBlueprint}
            </Link>
            <Link
              href="/features"
              className="px-6 py-3 rounded-lg border border-white/10 text-white hover:border-white/20 transition-colors"
            >
              {t.landing.learnMore}
            </Link>
          </div>
        </div>

        {/* Features */}
        <div id="features" className="max-w-7xl mx-auto px-6 py-24">
          <h2 className="text-3xl font-bold text-white text-center mb-16">
            {t.landing.featuresTitle}
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {/* Feature 1 */}
            <div className="bg-[#1A2942] rounded-xl border border-white/5 p-8">
              <div className="w-12 h-12 rounded-xl bg-[#00D4AA]/10 flex items-center justify-center mb-6">
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
                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                  />
                </svg>
              </div>
              <h3 className="text-xl font-semibold text-white mb-3">
                {t.landing.feature1Title}
              </h3>
              <p className="text-[#94A3B8]">
                {t.landing.feature1Desc}
              </p>
            </div>

            {/* Feature 2 */}
            <div className="bg-[#1A2942] rounded-xl border border-white/5 p-8">
              <div className="w-12 h-12 rounded-xl bg-[#3B82F6]/10 flex items-center justify-center mb-6">
                <svg
                  className="w-6 h-6 text-[#3B82F6]"
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
              <h3 className="text-xl font-semibold text-white mb-3">
                {t.landing.feature2Title}
              </h3>
              <p className="text-[#94A3B8]">
                {t.landing.feature2Desc}
              </p>
            </div>

            {/* Feature 3 */}
            <div className="bg-[#1A2942] rounded-xl border border-white/5 p-8">
              <div className="w-12 h-12 rounded-xl bg-[#F59E0B]/10 flex items-center justify-center mb-6">
                <svg
                  className="w-6 h-6 text-[#F59E0B]"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z"
                  />
                </svg>
              </div>
              <h3 className="text-xl font-semibold text-white mb-3">
                {t.landing.feature3Title}
              </h3>
              <p className="text-[#94A3B8]">
                {t.landing.feature3Desc}
              </p>
            </div>
          </div>
        </div>

        {/* CTA */}
        <div className="max-w-7xl mx-auto px-6 py-24">
          <div className="bg-gradient-to-r from-[#1A2942] to-[#243B53] rounded-2xl p-12 text-center">
            <h2 className="text-3xl font-bold text-white mb-4">
              {t.landing.ctaTitle}
            </h2>
            <p className="text-[#94A3B8] max-w-xl mx-auto mb-8">
              {t.landing.ctaDescription}
            </p>
            <Link
              href="/app/scan"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-lg bg-[#00D4AA] text-[#0F1B2A] font-semibold hover:bg-[#00D4AA]/90 transition-colors"
            >
              {t.landing.startScanning}
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
            </Link>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="relative z-10 border-t border-white/5">
        <div className="max-w-7xl mx-auto px-6 py-8">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <img
                src="https://gxwzhgqeloqbgptrgcvo.supabase.co/storage/v1/object/public/all/Adobe%20Express%20-%20file.png"
                alt="SnapPlan Logo"
                className="w-8 h-8 rounded-lg"
              />
              <span className="text-sm text-[#64748B]">
                {t.landing.footer}
              </span>
            </div>
            <p className="text-sm text-[#64748B]">
              {t.landing.footerTagline}
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
