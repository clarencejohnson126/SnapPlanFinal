"use client";

import { clsx } from "clsx";
import Link from "next/link";
import { useLanguage } from "@/lib/i18n";

export default function SettingsPage() {
  // Use the shared language context so the toggle actually switches the whole app
  // and stays in sync with the header toggle.
  const { language, setLanguage } = useLanguage();
  const de = language === "de";

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">
          {de ? "Einstellungen" : "Settings"}
        </h1>
        <p className="text-[#94A3B8] mt-1">
          {de
            ? "Konto und Einstellungen verwalten"
            : "Manage your account and preferences"}
        </p>
      </div>

      {/* Language settings */}
      <div className="bg-[#1A2942] rounded-xl border border-white/5 overflow-hidden">
        <div className="px-6 py-4 border-b border-white/5">
          <h2 className="font-semibold text-white">
            {de ? "Sprache" : "Language"}
          </h2>
          <p className="text-sm text-[#64748B] mt-1">
            {de
              ? "Wähle die bevorzugte Sprache für die Oberfläche"
              : "Choose your preferred language for the interface"}
          </p>
        </div>
        <div className="p-6">
          <div className="flex gap-4">
            <button
              onClick={() => setLanguage("de")}
              className={clsx(
                "flex-1 p-4 rounded-lg border transition-colors",
                language === "de"
                  ? "border-[#00D4AA] bg-[#00D4AA]/5"
                  : "border-white/10 hover:border-white/20"
              )}
            >
              <div className="flex items-center gap-3">
                <span className="text-2xl">🇩🇪</span>
                <div className="text-left">
                  <p className="font-medium text-white">Deutsch</p>
                  <p className="text-sm text-[#64748B]">German</p>
                </div>
              </div>
            </button>
            <button
              onClick={() => setLanguage("en")}
              className={clsx(
                "flex-1 p-4 rounded-lg border transition-colors",
                language === "en"
                  ? "border-[#00D4AA] bg-[#00D4AA]/5"
                  : "border-white/10 hover:border-white/20"
              )}
            >
              <div className="flex items-center gap-3">
                <span className="text-2xl">🇬🇧</span>
                <div className="text-left">
                  <p className="font-medium text-white">English</p>
                  <p className="text-sm text-[#64748B]">English</p>
                </div>
              </div>
            </button>
          </div>
        </div>
      </div>

      {/* Account settings */}
      <div className="bg-[#1A2942] rounded-xl border border-white/5 overflow-hidden">
        <div className="px-6 py-4 border-b border-white/5">
          <h2 className="font-semibold text-white">{de ? "Konto" : "Account"}</h2>
          <p className="text-sm text-[#64748B] mt-1">
            {de ? "Kontoeinstellungen verwalten" : "Manage your account settings"}
          </p>
        </div>
        <div className="divide-y divide-white/5">
          <div className="px-6 py-4 flex items-center justify-between">
            <div>
              <p className="font-medium text-white">
                {de ? "E-Mail-Benachrichtigungen" : "Email notifications"}
              </p>
              <p className="text-sm text-[#64748B]">
                {de
                  ? "E-Mail-Updates zu deinen Analysen erhalten"
                  : "Receive email updates about your analyses"}
              </p>
            </div>
            <button
              className="relative w-11 h-6 rounded-full bg-[#0F1B2A] border border-white/10 transition-colors"
              aria-label={de ? "E-Mail-Benachrichtigungen umschalten" : "Toggle email notifications"}
            >
              <span className="absolute left-1 top-1 w-4 h-4 rounded-full bg-[#64748B] transition-transform" />
            </button>
          </div>
          <div className="px-6 py-4 flex items-center justify-between">
            <div>
              <p className="font-medium text-white">
                {de ? "Zwei-Faktor-Authentifizierung" : "Two-factor authentication"}
              </p>
              <p className="text-sm text-[#64748B]">
                {de
                  ? "Zusätzliche Sicherheitsebene hinzufügen"
                  : "Add an extra layer of security"}
              </p>
            </div>
            <span className="px-2 py-1 rounded bg-[#64748B]/20 text-[#64748B] text-xs">
              {de ? "Demnächst" : "Coming Soon"}
            </span>
          </div>
        </div>
      </div>

      {/* Danger zone */}
      <div className="bg-[#1A2942] rounded-xl border border-red-500/20 overflow-hidden">
        <div className="px-6 py-4 border-b border-red-500/10">
          <h2 className="font-semibold text-red-400">
            {de ? "Gefahrenzone" : "Danger Zone"}
          </h2>
          <p className="text-sm text-[#64748B] mt-1">
            {de
              ? "Unwiderrufliche und destruktive Aktionen"
              : "Irreversible and destructive actions"}
          </p>
        </div>
        <div className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium text-white">
                {de ? "Konto löschen" : "Delete account"}
              </p>
              <p className="text-sm text-[#64748B]">
                {de
                  ? "Konto und alle Daten dauerhaft löschen"
                  : "Permanently delete your account and all data"}
              </p>
            </div>
            <button
              className="px-4 py-2 rounded-lg border border-red-500/30 text-red-400 hover:bg-red-500/10 transition-colors text-sm"
              disabled
            >
              {de ? "Konto löschen" : "Delete Account"}
            </button>
          </div>
        </div>
      </div>

      {/* Back link */}
      <Link
        href="/app"
        className="inline-flex items-center gap-2 text-sm text-[#00D4AA] hover:underline"
      >
        <svg
          className="w-4 h-4"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M10 19l-7-7m0 0l7-7m-7 7h18"
          />
        </svg>
        {de ? "Zurück zum Dashboard" : "Back to Dashboard"}
      </Link>
    </div>
  );
}
