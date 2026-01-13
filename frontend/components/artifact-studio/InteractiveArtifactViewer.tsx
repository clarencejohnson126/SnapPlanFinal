'use client';

import React, { useState, useRef, useCallback, useEffect } from 'react';
import { Volume2, VolumeX, ZoomIn, ZoomOut, RotateCcw, Layers, AlertTriangle, Info, X } from 'lucide-react';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface MaterialInfo {
  description: string;
  composition: string;
  dimensions: string;
}

interface FailureMode {
  type: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  description: string;
}

interface AcousticInfo {
  rating: string;
  notes: string;
}

interface FireInfo {
  rating: string;
  notes: string;
}

interface ComponentData {
  name: string;
  shortName: string;
  din: string;
  category: string[];
  material: MaterialInfo;
  function: string;
  failureModes: FailureMode[];
  installation: string[];
  crossTrade: string;
  acoustic: AcousticInfo;
  fire: FireInfo;
}

interface LayerCategory {
  id: string;
  name: string;
  color: string;
  description: string;
}

interface FailureScenario {
  id: string;
  name: string;
  description: string;
  affectedComponents: string[];
  severity: 'critical' | 'high' | 'medium';
  indicator: string;
}

interface InteractiveData {
  components: Record<string, ComponentData>;
  layerCategories: LayerCategory[];
  failureScenarios: FailureScenario[];
  svgContent: string;
  dimensions: { width: number; height: number };
}

interface InteractiveArtifactViewerProps {
  data: InteractiveData;
  title?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// SOUND EFFECTS HOOK
// ═══════════════════════════════════════════════════════════════════════════════

const useSoundEffects = () => {
  const audioContextRef = useRef<AudioContext | null>(null);

  const getAudioContext = useCallback(() => {
    if (!audioContextRef.current) {
      audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
    }
    return audioContextRef.current;
  }, []);

  const playHoverSound = useCallback(() => {
    try {
      const ctx = getAudioContext();
      const oscillator = ctx.createOscillator();
      const gainNode = ctx.createGain();

      oscillator.connect(gainNode);
      gainNode.connect(ctx.destination);

      oscillator.frequency.setValueAtTime(2400, ctx.currentTime);
      oscillator.frequency.exponentialRampToValueAtTime(1800, ctx.currentTime + 0.05);
      oscillator.type = 'sine';

      gainNode.gain.setValueAtTime(0.03, ctx.currentTime);
      gainNode.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.05);

      oscillator.start(ctx.currentTime);
      oscillator.stop(ctx.currentTime + 0.05);
    } catch (e) {
      // Audio not available
    }
  }, [getAudioContext]);

  const playClickSound = useCallback(() => {
    try {
      const ctx = getAudioContext();
      const oscillator = ctx.createOscillator();
      const gainNode = ctx.createGain();

      oscillator.connect(gainNode);
      gainNode.connect(ctx.destination);

      oscillator.frequency.setValueAtTime(800, ctx.currentTime);
      oscillator.frequency.exponentialRampToValueAtTime(400, ctx.currentTime + 0.08);
      oscillator.type = 'sine';

      gainNode.gain.setValueAtTime(0.08, ctx.currentTime);
      gainNode.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.1);

      oscillator.start(ctx.currentTime);
      oscillator.stop(ctx.currentTime + 0.1);
    } catch (e) {
      // Audio not available
    }
  }, [getAudioContext]);

  const playSelectSound = useCallback(() => {
    try {
      const ctx = getAudioContext();

      // First tone
      const osc1 = ctx.createOscillator();
      const gain1 = ctx.createGain();
      osc1.connect(gain1);
      gain1.connect(ctx.destination);
      osc1.frequency.setValueAtTime(600, ctx.currentTime);
      osc1.type = 'sine';
      gain1.gain.setValueAtTime(0.06, ctx.currentTime);
      gain1.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.08);
      osc1.start(ctx.currentTime);
      osc1.stop(ctx.currentTime + 0.08);

      // Second tone (slightly higher, delayed)
      const osc2 = ctx.createOscillator();
      const gain2 = ctx.createGain();
      osc2.connect(gain2);
      gain2.connect(ctx.destination);
      osc2.frequency.setValueAtTime(900, ctx.currentTime + 0.06);
      osc2.type = 'sine';
      gain2.gain.setValueAtTime(0.001, ctx.currentTime);
      gain2.gain.setValueAtTime(0.05, ctx.currentTime + 0.06);
      gain2.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.15);
      osc2.start(ctx.currentTime + 0.06);
      osc2.stop(ctx.currentTime + 0.15);
    } catch (e) {
      // Audio not available
    }
  }, [getAudioContext]);

  const playErrorSound = useCallback(() => {
    try {
      const ctx = getAudioContext();
      const oscillator = ctx.createOscillator();
      const gainNode = ctx.createGain();

      oscillator.connect(gainNode);
      gainNode.connect(ctx.destination);

      oscillator.frequency.setValueAtTime(200, ctx.currentTime);
      oscillator.frequency.setValueAtTime(150, ctx.currentTime + 0.1);
      oscillator.type = 'sine';

      gainNode.gain.setValueAtTime(0.06, ctx.currentTime);
      gainNode.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.2);

      oscillator.start(ctx.currentTime);
      oscillator.stop(ctx.currentTime + 0.2);
    } catch (e) {
      // Audio not available
    }
  }, [getAudioContext]);

  return { playHoverSound, playClickSound, playSelectSound, playErrorSound };
};

// ═══════════════════════════════════════════════════════════════════════════════
// INFO PANEL COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

const InfoPanel: React.FC<{
  componentId: string | null;
  components: Record<string, ComponentData>;
  onClose: () => void;
}> = ({ componentId, components, onClose }) => {
  const data = componentId ? components[componentId] : null;

  if (!data) {
    return (
      <div className="h-full flex items-center justify-center text-stone-500 font-serif italic px-6 text-center">
        Wählen Sie ein Bauteil aus der Zeichnung, um technische Informationen anzuzeigen.
      </div>
    );
  }

  const severityColors: Record<string, string> = {
    critical: 'bg-red-900/30 border-red-800 text-red-200',
    high: 'bg-orange-900/30 border-orange-800 text-orange-200',
    medium: 'bg-yellow-900/30 border-yellow-800 text-yellow-200',
    low: 'bg-stone-700/30 border-stone-600 text-stone-300'
  };

  // Safely get nested values with defaults
  const materialDesc = data.material?.description || data.name || 'Keine Beschreibung';
  const materialComp = data.material?.composition || '';
  const materialDim = data.material?.dimensions || '';
  const acousticRating = data.acoustic?.rating || '-';
  const acousticNotes = data.acoustic?.notes || '';
  const fireRating = data.fire?.rating || '-';
  const fireNotes = data.fire?.notes || '';
  const failureModes = data.failureModes || [];
  const installation = data.installation || [];
  const crossTrade = data.crossTrade || 'Keine Angaben';

  return (
    <div className="h-full overflow-y-auto custom-scrollbar">
      {/* Header */}
      <div className="sticky top-0 bg-stone-900 border-b border-stone-700 px-4 py-3 z-10">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="font-serif text-lg text-stone-100">{data.name || 'Unbekannt'}</h2>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-xs font-mono text-stone-400">{data.shortName || componentId}</span>
              {data.din && (
                <>
                  <span className="text-stone-600">•</span>
                  <span className="text-xs text-stone-500">{data.din}</span>
                </>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-stone-500 hover:text-stone-300 transition-colors p-1"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="px-4 py-4 space-y-5">
        {/* Material */}
        {(materialDesc || materialComp || materialDim) && (
          <section>
            <h3 className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">Material</h3>
            <div className="bg-stone-800/50 rounded p-3 space-y-2">
              {materialDesc && <p className="text-sm text-stone-200">{materialDesc}</p>}
              {materialComp && <p className="text-xs text-stone-400">{materialComp}</p>}
              {materialDim && <p className="text-xs text-stone-500 font-mono">{materialDim}</p>}
            </div>
          </section>
        )}

        {/* Function */}
        {data.function && (
          <section>
            <h3 className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">Funktion</h3>
            <p className="text-sm text-stone-300 leading-relaxed">{data.function}</p>
          </section>
        )}

        {/* Performance */}
        {(acousticRating !== '-' || fireRating !== '-') && (
          <section>
            <h3 className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">Leistungswerte</h3>
            <div className="grid grid-cols-2 gap-2">
              <div className="bg-stone-800/50 rounded p-2">
                <div className="text-[10px] text-stone-500 uppercase">Akustik</div>
                <div className="text-xs font-semibold text-stone-200 mt-0.5">{acousticRating}</div>
                {acousticNotes && <div className="text-[10px] text-stone-400 mt-1">{acousticNotes}</div>}
              </div>
              <div className="bg-stone-800/50 rounded p-2">
                <div className="text-[10px] text-stone-500 uppercase">Brandschutz</div>
                <div className="text-xs font-semibold text-stone-200 mt-0.5">{fireRating}</div>
                {fireNotes && <div className="text-[10px] text-stone-400 mt-1">{fireNotes}</div>}
              </div>
            </div>
          </section>
        )}

        {/* Failure Modes */}
        {failureModes.length > 0 && (
          <section>
            <h3 className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">Typische Fehler</h3>
            <div className="space-y-2">
              {failureModes.map((failure, idx) => (
                <div
                  key={idx}
                  className={`rounded p-2 border ${severityColors[failure.severity] || severityColors.low}`}
                >
                  <div className="text-xs font-semibold">{failure.type || 'Fehler'}</div>
                  {failure.description && <div className="text-[11px] mt-1 opacity-90">{failure.description}</div>}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Installation Notes */}
        {installation.length > 0 && (
          <section>
            <h3 className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">Einbauhinweise</h3>
            <ul className="space-y-1.5">
              {installation.map((note, idx) => (
                <li key={idx} className="text-sm text-stone-300 flex items-start gap-2">
                  <span className="text-stone-600 mt-1">›</span>
                  <span>{note}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Cross-Trade */}
        {crossTrade && crossTrade !== 'Keine Angaben' && (
          <section>
            <h3 className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">Gewerkekoordination</h3>
            <div className="bg-amber-900/20 border border-amber-800/50 rounded p-3">
              <p className="text-sm text-amber-200/90">{crossTrade}</p>
            </div>
          </section>
        )}

        {/* Categories */}
        {data.category && data.category.length > 0 && (
          <section>
            <h3 className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">Kategorien</h3>
            <div className="flex flex-wrap gap-1">
              {data.category.map((cat, idx) => (
                <span key={idx} className="px-2 py-1 bg-stone-800 text-stone-300 text-xs rounded">
                  {cat}
                </span>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════════
// LAYER PANEL COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

const LayerPanel: React.FC<{
  categories: LayerCategory[];
  activeCategory: string;
  setActiveCategory: (id: string) => void;
  failureScenarios: FailureScenario[];
  failureMode: string | null;
  setFailureMode: (id: string | null) => void;
  components: Record<string, ComponentData>;
  selectedComponent: string | null;
  onSelectComponent: (id: string) => void;
  onButtonClick: () => void;
}> = ({ categories, activeCategory, setActiveCategory, failureScenarios, failureMode, setFailureMode, components, selectedComponent, onSelectComponent, onButtonClick }) => {
  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="px-4 py-3 border-b border-stone-700">
        <h2 className="font-serif text-sm text-stone-200 flex items-center gap-2">
          <Layers className="w-4 h-4" />
          Ebenenfilter
        </h2>
      </div>

      {/* Category Filters */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-3 py-3">
        <div className="space-y-1">
          {categories.map(category => (
            <button
              key={category.id}
              onClick={() => {
                setActiveCategory(category.id);
                onButtonClick();
              }}
              className={`w-full text-left px-3 py-2 rounded transition-all ${
                activeCategory === category.id
                  ? 'bg-stone-700 text-stone-100'
                  : 'text-stone-400 hover:bg-stone-800 hover:text-stone-300'
              }`}
            >
              <div className="flex items-center gap-2">
                <div
                  className="w-3 h-3 rounded-sm"
                  style={{ backgroundColor: category.color }}
                />
                <span className="text-xs font-medium">{category.name}</span>
              </div>
              {activeCategory === category.id && (
                <p className="text-[10px] text-stone-500 mt-1 ml-5">{category.description}</p>
              )}
            </button>
          ))}
        </div>

        {/* Divider */}
        <div className="my-4 border-t border-stone-700" />

        {/* Component List - Clickable */}
        <div className="px-1 mb-4">
          <h3 className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-2 flex items-center gap-2">
            <Info className="w-3 h-3" />
            Bauteile ({Object.keys(components).length})
          </h3>
          <div className="space-y-1 max-h-48 overflow-y-auto">
            {Object.entries(components).map(([id, comp]) => (
              <button
                key={id}
                onClick={() => {
                  onSelectComponent(id);
                  onButtonClick();
                }}
                className={`w-full text-left px-3 py-2 rounded transition-all ${
                  selectedComponent === id
                    ? 'bg-[#00D4AA]/20 text-[#00D4AA] border border-[#00D4AA]/30'
                    : 'text-stone-400 hover:bg-stone-800 hover:text-stone-300'
                }`}
              >
                <div className="text-xs font-medium truncate">{comp.shortName}</div>
                <div className="text-[10px] text-stone-500 truncate">{comp.name}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Divider */}
        <div className="my-4 border-t border-stone-700" />

        {/* Failure Inspector */}
        <div className="px-1">
          <h3 className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-2 flex items-center gap-2">
            <AlertTriangle className="w-3 h-3" />
            Fehlerinspektor
          </h3>
          <div className="space-y-1">
            <button
              onClick={() => {
                setFailureMode(null);
                onButtonClick();
              }}
              className={`w-full text-left px-3 py-2 rounded text-xs transition-all ${
                !failureMode
                  ? 'bg-stone-700 text-stone-200'
                  : 'text-stone-500 hover:bg-stone-800'
              }`}
            >
              Keine Fehler anzeigen
            </button>
            {failureScenarios.map(scenario => (
              <button
                key={scenario.id}
                onClick={() => {
                  setFailureMode(failureMode === scenario.id ? null : scenario.id);
                  onButtonClick();
                }}
                className={`w-full text-left px-3 py-2 rounded transition-all ${
                  failureMode === scenario.id
                    ? scenario.severity === 'critical' ? 'bg-red-900/40 text-red-200' :
                      scenario.severity === 'high' ? 'bg-orange-900/40 text-orange-200' :
                      'bg-yellow-900/40 text-yellow-200'
                    : 'text-stone-500 hover:bg-stone-800 hover:text-stone-400'
                }`}
              >
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${
                    scenario.severity === 'critical' ? 'bg-red-500' :
                    scenario.severity === 'high' ? 'bg-orange-500' : 'bg-yellow-500'
                  }`} />
                  <span className="text-xs">{scenario.name}</span>
                </div>
                {failureMode === scenario.id && (
                  <p className="text-[10px] opacity-75 mt-1 ml-4">{scenario.indicator}</p>
                )}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-stone-700 bg-stone-900/50">
        <div className="text-[10px] text-stone-600 text-center">
          Klicken Sie auf ein Bauteil für Details
        </div>
      </div>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════════
// TOOLTIP COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

const Tooltip: React.FC<{
  componentId: string | null;
  components: Record<string, ComponentData>;
  position: { x: number; y: number };
}> = ({ componentId, components, position }) => {
  if (!componentId || !components[componentId]) return null;

  const data = components[componentId];

  return (
    <div
      className="absolute z-50 pointer-events-none"
      style={{
        left: position.x + 15,
        top: position.y - 10,
        maxWidth: '280px'
      }}
    >
      <div className="bg-stone-900 text-stone-100 px-3 py-2 rounded shadow-lg border border-stone-700">
        <div className="font-serif font-semibold text-sm">{data.name}</div>
        <div className="text-xs text-stone-400 mt-0.5">{data.din}</div>
      </div>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function InteractiveArtifactViewer({ data, title }: InteractiveArtifactViewerProps) {
  const [activeComponent, setActiveComponent] = useState<string | null>(null);
  const [selectedComponent, setSelectedComponent] = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState('all');
  const [failureMode, setFailureMode] = useState<string | null>(null);
  const [zoomLevel, setZoomLevel] = useState(1);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [tooltipPosition, setTooltipPosition] = useState({ x: 0, y: 0 });
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [lastHoveredComponent, setLastHoveredComponent] = useState<string | null>(null);
  const [showLayerPanel, setShowLayerPanel] = useState(true);
  const [showInfoPanel, setShowInfoPanel] = useState(true);

  const svgContainerRef = useRef<HTMLDivElement>(null);
  const { playHoverSound, playClickSound, playSelectSound, playErrorSound } = useSoundEffects();

  // Extract data
  const { components, layerCategories, failureScenarios, svgContent, dimensions } = data;

  // Get component opacity based on active category
  const getComponentOpacity = useCallback((componentId: string): number => {
    if (activeCategory === 'all') return 1;
    const component = components[componentId];
    if (!component) return 0.15;
    return component.category.includes(activeCategory) ? 1 : 0.15;
  }, [activeCategory, components]);

  // Get failure highlight color
  const getFailureHighlight = useCallback((componentId: string): string | null => {
    if (!failureMode) return null;
    const scenario = failureScenarios.find(f => f.id === failureMode);
    if (scenario && scenario.affectedComponents.includes(componentId)) {
      return scenario.severity === 'critical' ? '#B22222' :
             scenario.severity === 'high' ? '#CD5C5C' : '#DAA520';
    }
    return null;
  }, [failureMode, failureScenarios]);

  // Handle component hover
  const handleComponentHover = useCallback((componentId: string) => {
    if (soundEnabled && componentId !== lastHoveredComponent && components[componentId]) {
      playHoverSound();
      setLastHoveredComponent(componentId);
    }
    setActiveComponent(componentId);
  }, [soundEnabled, lastHoveredComponent, playHoverSound, components]);

  // Handle component click
  const handleComponentClick = useCallback((componentId: string) => {
    if (components[componentId]) {
      if (soundEnabled) {
        playSelectSound();
      }
      setSelectedComponent(componentId);
      setShowInfoPanel(true);
    }
  }, [soundEnabled, playSelectSound, components]);

  // Handle mouse move for tooltip
  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (svgContainerRef.current) {
      const rect = svgContainerRef.current.getBoundingClientRect();
      setTooltipPosition({
        x: e.clientX - rect.left,
        y: e.clientY - rect.top
      });
    }
  }, []);

  // Handle wheel for zoom
  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.1 : 0.1;
    setZoomLevel(prev => Math.min(Math.max(prev + delta, 0.5), 3));
  }, []);

  // Handle button click sound
  const handleButtonClick = useCallback(() => {
    if (soundEnabled) {
      playClickSound();
    }
  }, [soundEnabled, playClickSound]);

  // Reset view
  const resetView = useCallback(() => {
    setZoomLevel(1);
    setPanOffset({ x: 0, y: 0 });
    handleButtonClick();
  }, [handleButtonClick]);

  // Apply interactivity to SVG
  useEffect(() => {
    if (!svgContainerRef.current) return;

    const svgElement = svgContainerRef.current.querySelector('svg');
    if (!svgElement) return;

    // Apply zoom and pan transforms
    svgElement.style.transform = `scale(${zoomLevel}) translate(${panOffset.x}px, ${panOffset.y}px)`;
    svgElement.style.transformOrigin = 'center center';

    // Find all elements with IDs that match components
    Object.keys(components).forEach(componentId => {
      const elements = svgElement.querySelectorAll(`#${componentId}, [id="${componentId}"]`);
      elements.forEach(element => {
        const el = element as SVGElement;

        // Apply opacity based on category filter
        el.style.opacity = String(getComponentOpacity(componentId));

        // Apply failure highlight
        const highlight = getFailureHighlight(componentId);
        if (highlight) {
          el.style.filter = `drop-shadow(0 0 4px ${highlight})`;
          const paths = el.querySelectorAll('path, rect, circle, ellipse, polygon');
          paths.forEach(path => {
            (path as SVGElement).style.stroke = highlight;
            (path as SVGElement).style.strokeWidth = '2';
          });
        } else {
          el.style.filter = '';
        }

        // Add hover effect
        el.style.cursor = 'pointer';
        el.style.transition = 'opacity 0.2s, filter 0.2s';

        // Add event listeners
        el.onmouseenter = () => handleComponentHover(componentId);
        el.onclick = (e) => {
          e.stopPropagation();
          handleComponentClick(componentId);
        };
      });
    });
  }, [components, getComponentOpacity, getFailureHighlight, handleComponentHover, handleComponentClick, zoomLevel, panOffset]);

  return (
    <div className="h-full w-full bg-stone-950 text-stone-300 flex flex-col overflow-hidden rounded-lg border border-stone-800">
      {/* Top Bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-stone-900 border-b border-stone-800">
        <div className="flex items-center gap-4">
          {title && (
            <h1 className="font-serif text-sm font-semibold text-stone-200">{title}</h1>
          )}
          <div className="text-xs text-stone-500">
            Interaktives Detail
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Sound Toggle */}
          <button
            onClick={() => {
              setSoundEnabled(!soundEnabled);
              if (!soundEnabled) playClickSound();
            }}
            className={`p-2 rounded transition-colors ${
              soundEnabled ? 'text-stone-300 bg-stone-800' : 'text-stone-600 hover:text-stone-400'
            }`}
            title={soundEnabled ? 'Ton aus' : 'Ton an'}
          >
            {soundEnabled ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
          </button>

          {/* Zoom Controls */}
          <div className="flex items-center gap-1 bg-stone-800 rounded px-2 py-1">
            <button
              onClick={() => { setZoomLevel(prev => Math.max(prev - 0.25, 0.5)); handleButtonClick(); }}
              className="text-stone-400 hover:text-stone-200 transition-colors p-1"
            >
              <ZoomOut className="w-4 h-4" />
            </button>
            <span className="text-xs text-stone-400 w-12 text-center">{Math.round(zoomLevel * 100)}%</span>
            <button
              onClick={() => { setZoomLevel(prev => Math.min(prev + 0.25, 3)); handleButtonClick(); }}
              className="text-stone-400 hover:text-stone-200 transition-colors p-1"
            >
              <ZoomIn className="w-4 h-4" />
            </button>
            <button
              onClick={resetView}
              className="text-stone-400 hover:text-stone-200 transition-colors p-1 ml-1"
              title="Ansicht zurücksetzen"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
          </div>

          {/* Panel Toggles */}
          <button
            onClick={() => { setShowLayerPanel(!showLayerPanel); handleButtonClick(); }}
            className={`p-2 rounded transition-colors ${
              showLayerPanel ? 'text-stone-300 bg-stone-800' : 'text-stone-600 hover:text-stone-400'
            }`}
            title="Ebenen"
          >
            <Layers className="w-4 h-4" />
          </button>
          <button
            onClick={() => { setShowInfoPanel(!showInfoPanel); handleButtonClick(); }}
            className={`p-2 rounded transition-colors ${
              showInfoPanel ? 'text-stone-300 bg-stone-800' : 'text-stone-600 hover:text-stone-400'
            }`}
            title="Info"
          >
            <Info className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Layer Panel */}
        {showLayerPanel && (
          <div className="w-56 border-r border-stone-800 bg-stone-900/50 flex-shrink-0">
            <LayerPanel
              categories={layerCategories}
              activeCategory={activeCategory}
              setActiveCategory={setActiveCategory}
              failureScenarios={failureScenarios}
              failureMode={failureMode}
              setFailureMode={setFailureMode}
              components={components}
              selectedComponent={selectedComponent}
              onSelectComponent={(id) => {
                if (soundEnabled) playSelectSound();
                setSelectedComponent(id);
                setShowInfoPanel(true);
              }}
              onButtonClick={handleButtonClick}
            />
          </div>
        )}

        {/* SVG Viewer */}
        <div
          ref={svgContainerRef}
          className="flex-1 relative overflow-hidden bg-stone-950"
          onMouseMove={handleMouseMove}
          onWheel={handleWheel}
          onMouseLeave={() => setActiveComponent(null)}
        >
          {/* Background Grid */}
          <div
            className="absolute inset-0 opacity-10"
            style={{
              backgroundImage: `
                linear-gradient(to right, #374151 1px, transparent 1px),
                linear-gradient(to bottom, #374151 1px, transparent 1px)
              `,
              backgroundSize: '20px 20px'
            }}
          />

          {/* SVG Content */}
          <div
            className="w-full h-full flex items-center justify-center p-8"
            dangerouslySetInnerHTML={{ __html: svgContent }}
          />

          {/* Tooltip */}
          <Tooltip
            componentId={activeComponent}
            components={components}
            position={tooltipPosition}
          />
        </div>

        {/* Info Panel */}
        {showInfoPanel && (
          <div className="w-80 border-l border-stone-800 bg-stone-900/50 flex-shrink-0">
            <InfoPanel
              componentId={selectedComponent}
              components={components}
              onClose={() => setSelectedComponent(null)}
            />
          </div>
        )}
      </div>

      {/* Bottom Bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-stone-900 border-t border-stone-800">
        <div className="text-xs text-stone-500">
          {activeComponent ? (
            <span>
              <span className="text-stone-400">{components[activeComponent]?.shortName || activeComponent}</span>
              {' • '}
              <span>{components[activeComponent]?.din || 'Unbekannt'}</span>
            </span>
          ) : (
            'Fahren Sie mit der Maus über ein Bauteil'
          )}
        </div>
        <div className="text-xs text-stone-600">
          {Object.keys(components).length} Komponenten
        </div>
      </div>

      {/* Custom scrollbar styles */}
      <style jsx>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 6px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: transparent;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: #44403c;
          border-radius: 3px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: #57534e;
        }
      `}</style>
    </div>
  );
}
