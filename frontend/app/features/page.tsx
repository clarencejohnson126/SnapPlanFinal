"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, FileText, Pencil, Calculator, FolderOpen, Sparkles, CheckCircle, Zap, X } from "lucide-react";

export default function FeaturesPage() {
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [lightboxImage, setLightboxImage] = useState("");

  const openLightbox = (src: string) => {
    setLightboxImage(src);
    setLightboxOpen(true);
  };

  return (
    <div className="min-h-screen bg-[#0F172A]">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-[#0F172A]/95 backdrop-blur border-b border-white/5">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <Link
            href="/"
            className="flex items-center gap-2 text-[#94A3B8] hover:text-white transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
            <span>Zurück</span>
          </Link>
          <Link
            href="/app/scan"
            className="px-4 py-2 bg-[#00D4AA] text-[#0F172A] rounded-lg font-medium hover:bg-[#00D4AA]/90 transition-colors"
          >
            Jetzt starten
          </Link>
        </div>
      </header>

      {/* Hero */}
      <section className="py-16 px-4">
        <div className="max-w-4xl mx-auto text-center">
          <h1 className="text-4xl md:text-5xl font-bold text-white mb-6">
            Alles, was SnapPlan kann
          </h1>
          <p className="text-xl text-[#94A3B8] max-w-2xl mx-auto">
            Von der automatischen Flächenextraktion bis zu interaktiven Baudetail-Skizzen –
            entdecken Sie die Werkzeuge, die Ihre Arbeit mit Bauplänen revolutionieren.
          </p>
        </div>
      </section>

      {/* Features */}
      <section className="py-12 px-4">
        <div className="max-w-6xl mx-auto space-y-16">

          {/* Feature 1: M² Extraction */}
          <div className="grid md:grid-cols-2 gap-8 items-center">
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1 bg-[#00D4AA]/10 text-[#00D4AA] rounded-full text-sm mb-4">
                <FileText className="w-4 h-4" />
                Kernfunktion
              </div>
              <h2 className="text-3xl font-bold text-white mb-4">
                M² aus Aufmaßen extrahieren
              </h2>
              <p className="text-[#94A3B8] mb-6">
                Laden Sie Ihre deutschen Baupläne hoch und erhalten Sie sofort alle Raumflächen
                mit vollständiger Nachvollziehbarkeit. Keine Halluzination – jede Zahl stammt
                direkt aus dem PDF.
              </p>
              <ul className="space-y-3">
                <li className="flex items-start gap-3 text-[#94A3B8]">
                  <CheckCircle className="w-5 h-5 text-[#00D4AA] mt-0.5 flex-shrink-0" />
                  <span><strong className="text-white">Automatische Stillerkennung:</strong> Haardtring, LeiQ und Omniturm Formate</span>
                </li>
                <li className="flex items-start gap-3 text-[#94A3B8]">
                  <CheckCircle className="w-5 h-5 text-[#00D4AA] mt-0.5 flex-shrink-0" />
                  <span><strong className="text-white">NRF/NGF Extraktion:</strong> Netto-Raumfläche mit deutschem Dezimalkomma</span>
                </li>
                <li className="flex items-start gap-3 text-[#94A3B8]">
                  <CheckCircle className="w-5 h-5 text-[#00D4AA] mt-0.5 flex-shrink-0" />
                  <span><strong className="text-white">Vollständiger Audit-Trail:</strong> Seitenzahl, Bounding Box, Rohtext, Konfidenz</span>
                </li>
                <li className="flex items-start gap-3 text-[#94A3B8]">
                  <CheckCircle className="w-5 h-5 text-[#00D4AA] mt-0.5 flex-shrink-0" />
                  <span><strong className="text-white">Export:</strong> Excel und CSV mit deutscher Formatierung</span>
                </li>
              </ul>
            </div>
            <div className="bg-[#1A2942] rounded-2xl p-8 border border-white/5">
              <div className="space-y-4">
                <div className="flex items-center justify-between p-3 bg-[#0F172A] rounded-lg">
                  <span className="text-[#94A3B8]">Büro 2.01</span>
                  <span className="text-white font-mono">24,56 m²</span>
                </div>
                <div className="flex items-center justify-between p-3 bg-[#0F172A] rounded-lg">
                  <span className="text-[#94A3B8]">Flur 2.02</span>
                  <span className="text-white font-mono">12,80 m²</span>
                </div>
                <div className="flex items-center justify-between p-3 bg-[#0F172A] rounded-lg">
                  <span className="text-[#94A3B8]">WC 2.03</span>
                  <span className="text-white font-mono">4,25 m²</span>
                </div>
                <div className="mt-4 pt-4 border-t border-white/10 flex items-center justify-between">
                  <span className="text-[#94A3B8]">Gesamt</span>
                  <span className="text-[#00D4AA] font-mono font-bold">41,61 m²</span>
                </div>
              </div>
            </div>
          </div>

          {/* Feature 2: Skizzen Studio */}
          <div className="grid md:grid-cols-2 gap-8 items-center">
            <div className="order-2 md:order-1 bg-[#1A2942] rounded-2xl p-2 border border-white/5 overflow-hidden">
              <img
                src="https://gxwzhgqeloqbgptrgcvo.supabase.co/storage/v1/object/public/all/Screenshot%202026-01-13%20at%2016.00.09.png"
                alt="Skizzen Studio - Interaktive Baudetail-Skizze"
                className="w-full h-auto rounded-lg cursor-pointer hover:opacity-90 transition-opacity"
                onClick={() => openLightbox("https://gxwzhgqeloqbgptrgcvo.supabase.co/storage/v1/object/public/all/Screenshot%202026-01-13%20at%2016.00.09.png")}
              />
              <p className="text-center text-[#64748B] text-xs mt-2">Klicken zum Vergrößern</p>
            </div>
            <div className="order-1 md:order-2">
              <div className="inline-flex items-center gap-2 px-3 py-1 bg-purple-500/10 text-purple-400 rounded-full text-sm mb-4">
                <Pencil className="w-4 h-4" />
                KI-Powered
              </div>
              <h2 className="text-3xl font-bold text-white mb-4">
                Skizzen Studio
              </h2>
              <p className="text-[#94A3B8] mb-6">
                Beschreiben Sie das gewünschte Baudetail in natürlicher Sprache und erhalten Sie
                eine interaktive, technisch korrekte Skizze – generiert von Claude AI.
              </p>
              <ul className="space-y-3">
                <li className="flex items-start gap-3 text-[#94A3B8]">
                  <CheckCircle className="w-5 h-5 text-purple-400 mt-0.5 flex-shrink-0" />
                  <span><strong className="text-white">Interaktive SVG-Grafiken:</strong> Klickbare Komponenten mit Tooltips</span>
                </li>
                <li className="flex items-start gap-3 text-[#94A3B8]">
                  <CheckCircle className="w-5 h-5 text-purple-400 mt-0.5 flex-shrink-0" />
                  <span><strong className="text-white">DIN-Standards:</strong> Technisch korrekte Materialangaben</span>
                </li>
                <li className="flex items-start gap-3 text-[#94A3B8]">
                  <CheckCircle className="w-5 h-5 text-purple-400 mt-0.5 flex-shrink-0" />
                  <span><strong className="text-white">Gewerke-Vorlagen:</strong> Trockenbau, Bodenbelag, Elektro, Dämmung</span>
                </li>
                <li className="flex items-start gap-3 text-[#94A3B8]">
                  <CheckCircle className="w-5 h-5 text-purple-400 mt-0.5 flex-shrink-0" />
                  <span><strong className="text-white">Teilbare URLs:</strong> Skizzen per Link versenden</span>
                </li>
              </ul>
            </div>
          </div>

          {/* Feature 3: Gewerke Rechner */}
          <div className="grid md:grid-cols-2 gap-8 items-center">
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1 bg-orange-500/10 text-orange-400 rounded-full text-sm mb-4">
                <Calculator className="w-4 h-4" />
                Fachspezifisch
              </div>
              <h2 className="text-3xl font-bold text-white mb-4">
                Gewerke-Rechner
              </h2>
              <p className="text-[#94A3B8] mb-6">
                Spezialisierte Berechnungsmodule für verschiedene Gewerke. Von der Türenliste
                bis zur Trockenbaufläche – präzise Mengenermittlung für Ihre Kalkulation.
              </p>
              <ul className="space-y-3">
                <li className="flex items-start gap-3 text-[#94A3B8]">
                  <CheckCircle className="w-5 h-5 text-orange-400 mt-0.5 flex-shrink-0" />
                  <span><strong className="text-white">Türen:</strong> Extraktion aus Türenlisten mit T30/T90 Klassifizierung</span>
                </li>
                <li className="flex items-start gap-3 text-[#94A3B8]">
                  <CheckCircle className="w-5 h-5 text-orange-400 mt-0.5 flex-shrink-0" />
                  <span><strong className="text-white">Bodenbelag:</strong> NRF-basierte Flächenberechnung</span>
                </li>
                <li className="flex items-start gap-3 text-[#94A3B8]">
                  <CheckCircle className="w-5 h-5 text-orange-400 mt-0.5 flex-shrink-0" />
                  <span><strong className="text-white">Trockenbau:</strong> Umfang × Wandhöhe Berechnung</span>
                </li>
                <li className="flex items-start gap-3 text-[#94A3B8]">
                  <CheckCircle className="w-5 h-5 text-orange-400 mt-0.5 flex-shrink-0" />
                  <span><strong className="text-white">Materialprojektion:</strong> Gerüst, Estrich, Abdichtung</span>
                </li>
              </ul>
            </div>
            <div className="bg-[#1A2942] rounded-2xl p-8 border border-white/5">
              <div className="space-y-4">
                <h3 className="text-white font-medium mb-4">Türenliste Export</h3>
                <div className="grid grid-cols-3 gap-3 text-sm">
                  <div className="p-3 bg-[#0F172A] rounded-lg text-center">
                    <p className="text-2xl font-bold text-white">24</p>
                    <p className="text-[#64748B]">Standard</p>
                  </div>
                  <div className="p-3 bg-[#0F172A] rounded-lg text-center">
                    <p className="text-2xl font-bold text-orange-400">8</p>
                    <p className="text-[#64748B]">T30-RS</p>
                  </div>
                  <div className="p-3 bg-[#0F172A] rounded-lg text-center">
                    <p className="text-2xl font-bold text-red-400">3</p>
                    <p className="text-[#64748B]">T90</p>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Feature 4: Projects */}
          <div className="grid md:grid-cols-2 gap-8 items-center">
            <div className="order-2 md:order-1 bg-[#1A2942] rounded-2xl p-8 border border-white/5">
              <div className="space-y-3">
                <div className="flex items-center gap-3 p-3 bg-[#0F172A] rounded-lg">
                  <FolderOpen className="w-5 h-5 text-blue-400" />
                  <div>
                    <p className="text-white font-medium">Neubau Musterstraße 12</p>
                    <p className="text-[#64748B] text-sm">5 Pläne • 127 Räume</p>
                  </div>
                </div>
                <div className="flex items-center gap-3 p-3 bg-[#0F172A] rounded-lg">
                  <FolderOpen className="w-5 h-5 text-blue-400" />
                  <div>
                    <p className="text-white font-medium">Bürogebäude West</p>
                    <p className="text-[#64748B] text-sm">12 Pläne • 342 Räume</p>
                  </div>
                </div>
                <div className="flex items-center gap-3 p-3 bg-[#0F172A] rounded-lg">
                  <FolderOpen className="w-5 h-5 text-blue-400" />
                  <div>
                    <p className="text-white font-medium">Sanierung Altbau</p>
                    <p className="text-[#64748B] text-sm">3 Pläne • 48 Räume</p>
                  </div>
                </div>
              </div>
            </div>
            <div className="order-1 md:order-2">
              <div className="inline-flex items-center gap-2 px-3 py-1 bg-blue-500/10 text-blue-400 rounded-full text-sm mb-4">
                <FolderOpen className="w-4 h-4" />
                Organisation
              </div>
              <h2 className="text-3xl font-bold text-white mb-4">
                Projekte verwalten
              </h2>
              <p className="text-[#94A3B8] mb-6">
                Organisieren Sie Ihre Baupläne in Projekten. Laden Sie mehrere PDFs hoch,
                vergleichen Sie Extraktionsergebnisse und behalten Sie den Überblick.
              </p>
              <ul className="space-y-3">
                <li className="flex items-start gap-3 text-[#94A3B8]">
                  <CheckCircle className="w-5 h-5 text-blue-400 mt-0.5 flex-shrink-0" />
                  <span><strong className="text-white">Projektordner:</strong> Alle Pläne eines Bauvorhabens zusammen</span>
                </li>
                <li className="flex items-start gap-3 text-[#94A3B8]">
                  <CheckCircle className="w-5 h-5 text-blue-400 mt-0.5 flex-shrink-0" />
                  <span><strong className="text-white">Verlauf:</strong> Alle Extraktionen mit Zeitstempel</span>
                </li>
                <li className="flex items-start gap-3 text-[#94A3B8]">
                  <CheckCircle className="w-5 h-5 text-blue-400 mt-0.5 flex-shrink-0" />
                  <span><strong className="text-white">Schnellscan:</strong> Ad-hoc Extraktion ohne Projekt</span>
                </li>
              </ul>
            </div>
          </div>

        </div>
      </section>

      {/* CTA */}
      <section className="py-16 px-4">
        <div className="max-w-4xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 px-4 py-2 bg-[#00D4AA]/10 text-[#00D4AA] rounded-full mb-6">
            <Zap className="w-5 h-5" />
            Jetzt kostenlos testen
          </div>
          <h2 className="text-3xl font-bold text-white mb-4">
            Bereit, Zeit zu sparen?
          </h2>
          <p className="text-[#94A3B8] mb-8 max-w-xl mx-auto">
            Laden Sie Ihren ersten Bauplan hoch und erleben Sie, wie schnell und präzise
            SnapPlan Ihre Daten extrahiert.
          </p>
          <Link
            href="/app/scan"
            className="inline-flex items-center gap-2 px-6 py-3 bg-[#00D4AA] text-[#0F172A] rounded-lg font-medium hover:bg-[#00D4AA]/90 transition-colors"
          >
            Ersten Plan hochladen
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 px-4 border-t border-white/5">
        <div className="max-w-6xl mx-auto text-center text-[#64748B] text-sm">
          SnapPlan - Deterministische Bauplan-Analyse
        </div>
      </footer>

      {/* Lightbox Modal */}
      {lightboxOpen && (
        <div
          className="fixed inset-0 z-[100] bg-black/90 flex items-center justify-center p-4"
          onClick={() => setLightboxOpen(false)}
        >
          <button
            className="absolute top-4 right-4 p-2 text-white/70 hover:text-white transition-colors"
            onClick={() => setLightboxOpen(false)}
          >
            <X className="w-8 h-8" />
          </button>
          <img
            src={lightboxImage}
            alt="Vergrößerte Ansicht"
            className="max-w-full max-h-[90vh] object-contain rounded-lg"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </div>
  );
}
