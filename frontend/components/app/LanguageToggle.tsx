"use client";

import { clsx } from "clsx";
import { useLanguage } from "@/lib/i18n";

export function LanguageToggle() {
  const { language, setLanguage } = useLanguage();

  return (
    <div className="flex items-center bg-[#1A2942] rounded-lg p-0.5">
      <button
        onClick={() => setLanguage("de")}
        className={clsx(
          "px-3 py-1.5 text-xs font-medium rounded-md transition-colors",
          language === "de"
            ? "bg-[#00D4AA] text-[#0F1B2A]"
            : "text-white/60 hover:text-white"
        )}
      >
        DE
      </button>
      <button
        onClick={() => setLanguage("en")}
        className={clsx(
          "px-3 py-1.5 text-xs font-medium rounded-md transition-colors",
          language === "en"
            ? "bg-[#00D4AA] text-[#0F1B2A]"
            : "text-white/60 hover:text-white"
        )}
      >
        EN
      </button>
    </div>
  );
}
