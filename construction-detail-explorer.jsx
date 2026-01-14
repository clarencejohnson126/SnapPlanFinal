import React, { useState, useRef, useEffect, useCallback } from 'react';

// ═══════════════════════════════════════════════════════════════════════════════
// CONSTRUCTION DETAIL EXPLORER
// Trockenbauwand → Anschluss → Doppelboden (Raised Access Floor)
// Premium Engineering Reference Tool
// ═══════════════════════════════════════════════════════════════════════════════

// Sound utility hook for subtle audio feedback
const useSoundEffects = () => {
  const audioContextRef = useRef(null);
  
  const getAudioContext = useCallback(() => {
    if (!audioContextRef.current) {
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
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

// Component database with comprehensive technical information
const COMPONENT_DATA = {
  'uw-profile-bottom': {
    name: 'UW-Profil (Bodenprofil)',
    shortName: 'UW 75',
    din: 'DIN 18182-1',
    category: ['load-bearing', 'fasteners'],
    material: {
      description: 'Verzinktes Stahlblech, 0,6 mm Materialstärke',
      composition: 'Stahl S235, feuerverzinkt nach DIN EN 10346',
      dimensions: 'UW 75 × 40 mm, Länge 3000/4000 mm'
    },
    function: 'Das UW-Profil bildet den unteren Anschluss der Trockenbauwand und dient als Führungsschiene für die CW-Ständerprofile. Es überträgt keine Vertikallasten, sondern fixiert die Wandkonstruktion horizontal.',
    failureModes: [
      { type: 'Schallbrücke', severity: 'high', description: 'Direkter Kontakt zum Rohboden ohne Trennstreifen führt zu Körperschallübertragung (bis zu 10 dB Verschlechterung)' },
      { type: 'Korrosion', severity: 'medium', description: 'Bei Feuchtigkeitseinwirkung im Bodenbereich ohne ausreichende Beschichtung' },
      { type: 'Fehlende Befestigung', severity: 'high', description: 'Dübelabstände > 800 mm führen zu Instabilität der Gesamtkonstruktion' }
    ],
    installation: [
      'Trennstreifen unterlegen (PE-Schaum oder Bitumenfilz)',
      'Dübelabstand max. 800 mm, bei Schallschutzanforderungen max. 500 mm',
      'Stoßverbindungen mit 100 mm Überlappung oder Stoßlasche',
      'Ausrichtung mit Laser oder Schlagschnur'
    ],
    crossTrade: 'Abstimmung mit Doppelbodenleger erforderlich: UW-Profil wird auf Rohboden montiert, BEVOR Doppelboden verlegt wird. Anschlussdetail an Doppelbodenkante klären.',
    acoustic: {
      rating: 'Kritisches Element für Schallschutz',
      notes: 'Ohne Trennstreifen: Rw-Verschlechterung 5-10 dB. Mit 3 mm PE-Streifen: Körperschallentkopplung gewährleistet.'
    },
    fire: {
      rating: 'F30-F90 möglich',
      notes: 'Stahlprofil ist nicht brennbar (A1). Feuerwiderstand abhängig von Gesamtaufbau und Beplankung.'
    }
  },
  'uw-profile-top': {
    name: 'UW-Profil (Deckenprofil)',
    shortName: 'UW 75',
    din: 'DIN 18182-1',
    category: ['load-bearing', 'fasteners'],
    material: {
      description: 'Verzinktes Stahlblech, 0,6 mm Materialstärke',
      composition: 'Stahl S235, feuerverzinkt nach DIN EN 10346',
      dimensions: 'UW 75 × 40 mm'
    },
    function: 'Oberer horizontaler Abschluss der Ständerwandkonstruktion. Nimmt Bewegungen aus Deckendurchbiegung auf.',
    failureModes: [
      { type: 'Starre Verbindung', severity: 'high', description: 'Fehlende Gleitverbindung bei abgehängten Decken führt zu Rissen' },
      { type: 'Schallbrücke', severity: 'medium', description: 'Direkter Kontakt zur Rohdecke ohne Dämmstreifen' }
    ],
    installation: [
      'Bei Massivdecken: Direktbefestigung mit Trennstreifen',
      'Bei abgehängten Decken: Gleitanschluss vorsehen',
      'Dübelabstand analog Bodenprofil'
    ],
    crossTrade: 'Koordination mit Deckenbauer und ggf. Lüftungsgewerken',
    acoustic: { rating: 'Wichtig', notes: 'Trennstreifen obligatorisch bei Schallschutzanforderungen ≥ Rw 42 dB' },
    fire: { rating: 'F30-F90', notes: 'Anschluss an Decke muss brandschutztechnisch geschlossen sein' }
  },
  'cw-profile': {
    name: 'CW-Ständerprofil',
    shortName: 'CW 75',
    din: 'DIN 18182-1',
    category: ['load-bearing'],
    material: {
      description: 'Verzinktes C-Profil mit H-Stanzungen',
      composition: 'Stahl S235, feuerverzinkt, 0,6 mm',
      dimensions: 'CW 75 × 50 mm, Länge nach Raumhöhe'
    },
    function: 'Vertikale Tragstruktur der Trockenbauwand. Die CW-Profile nehmen die Beplankung auf und leiten horizontale Lasten (Wind, Stoß) in die UW-Profile ab.',
    failureModes: [
      { type: 'Falscher Achsabstand', severity: 'high', description: 'Achsabstand > 625 mm reduziert Tragfähigkeit und Beplankungsstabilität erheblich' },
      { type: 'Verdrehung', severity: 'medium', description: 'Unsachgemäße Einstellung in UW-Profile führt zu Welligkeit der Beplankung' },
      { type: 'Fehlende Aussteifung', severity: 'medium', description: 'Bei Wandhöhen > 3,50 m zusätzliche UA-Profile oder Traversen erforderlich' }
    ],
    installation: [
      'Achsabstand 625 mm (bei 12,5 mm Platten) oder 416,7 mm (bei 9,5 mm)',
      'Profile mit offener Seite in Montagerichtung einsetzen',
      'Ca. 10-15 mm kürzer als lichte Raumhöhe ablängen',
      'Nicht mit UW-Profilen verschrauben (Schallbrücke!)'
    ],
    crossTrade: 'Elektroinstallation erfolgt durch H-Stanzungen. Koordination der Leitungsführung.',
    acoustic: { rating: 'Konstruktiv wichtig', notes: 'Entkoppelte Ständerreihen (getrennte CW-Profile) für Rw > 55 dB' },
    fire: { rating: 'A1', notes: 'Nicht brennbar. Tragfähigkeit bei Brandbeanspruchung zeitlich begrenzt.' }
  },
  'ua-profile': {
    name: 'UA-Aussteifungsprofil',
    shortName: 'UA 75',
    din: 'DIN 18182-1',
    category: ['load-bearing'],
    material: {
      description: 'Verstärktes U-Profil, 2,0 mm Materialstärke',
      composition: 'Stahl S235, feuerverzinkt',
      dimensions: 'UA 75 × 40 × 2,0 mm'
    },
    function: 'Verstärkungsprofil für erhöhte statische Anforderungen: Türzargen, Wandanschlüsse, Konsollasten, Wandhöhen > 3,50 m.',
    failureModes: [
      { type: 'Unterdimensionierung', severity: 'high', description: 'Standardprofil CW statt UA bei Türöffnungen führt zu Zargenversagen' },
      { type: 'Fehlende Winkelverbinder', severity: 'medium', description: 'UA-Profile müssen oben und unten mit Winkeln befestigt werden' }
    ],
    installation: [
      'Befestigung mit speziellen UA-Winkeln an Decke und Boden',
      'Bei Türzargen: UA-Profile 150 mm über Sturzunterkante führen',
      'Konsollasten: Statischen Nachweis führen'
    ],
    crossTrade: 'Abstimmung mit Türlieferant bezüglich Zargengewicht und Befestigungsart',
    acoustic: { rating: 'Neutral', notes: 'Kein direkter Einfluss auf Schalldämmung' },
    fire: { rating: 'A1', notes: 'Erhöhte Standsicherheit im Brandfall durch stärkere Wandstärke' }
  },
  'gypsum-board-outer': {
    name: 'Gipskartonplatte (Außenlage)',
    shortName: 'GKB 12,5',
    din: 'DIN EN 520 / DIN 18180',
    category: ['finishing', 'fire-protection'],
    material: {
      description: 'Gipskartonplatte Typ A, Bauplatte',
      composition: 'Gipskern mit Kartonummantelung, ggf. imprägniert (GKBI)',
      dimensions: '12,5 × 1250 × 2000/2600 mm'
    },
    function: 'Äußere Beplankungsschicht. Bildet die raumseitige Oberfläche, nimmt Oberflächenlasten auf und trägt zum Brand- und Schallschutz bei.',
    failureModes: [
      { type: 'Schraubenüberstand', severity: 'low', description: 'Schraubenköpfe nicht versenkt, sichtbar nach Verspachtelung' },
      { type: 'Fugenrisse', severity: 'medium', description: 'Fehlende oder falsche Fugenspachtelung, unzureichende Bewehrung' },
      { type: 'Feuchteschaden', severity: 'high', description: 'Standardplatten in Feuchträumen führen zu Schimmel und Zerfall' }
    ],
    installation: [
      'Schraubenabstand Rand 15 cm, Feld 25 cm',
      'Platten mit 1 cm Bodenabstand montieren',
      'Fugenversatz zur Innenlage mind. 400 mm',
      'Schraubenlänge: Plattenstärke + 10 mm Einschraubtiefe'
    ],
    crossTrade: 'Malerarbeiten erst nach vollständiger Austrocknung der Spachtelmasse',
    acoustic: { rating: 'Masserelevant', notes: 'Flächenmasse ca. 10 kg/m². Doppelbeplankung erhöht Rw um ca. 5 dB' },
    fire: { rating: 'A2-s1, d0', notes: 'Schwerentflammbar. F30 mit Einfachbeplankung, F90 mit Mehrfachbeplankung möglich.' }
  },
  'gypsum-board-inner': {
    name: 'Gipskartonplatte (Innenlage)',
    shortName: 'GKB 12,5',
    din: 'DIN EN 520 / DIN 18180',
    category: ['finishing', 'fire-protection'],
    material: {
      description: 'Gipskartonplatte Typ A oder DF (Feuerschutz)',
      composition: 'Bei Brandschutzanforderungen: GKF mit Glasfaserverstärkung',
      dimensions: '12,5 × 1250 × 2000/2600 mm'
    },
    function: 'Innere Beplankungsschicht bei Doppelbeplankung. Erhöht Flächenmasse, verbessert Schall- und Brandschutz.',
    failureModes: [
      { type: 'Fehlender Fugenversatz', severity: 'high', description: 'Durchgehende Fugen reduzieren Brandschutz drastisch' },
      { type: 'Plattentyp-Verwechslung', severity: 'high', description: 'Standard-GKB statt GKF bei F90-Anforderung' }
    ],
    installation: [
      'Fugen zur Außenlage um mind. 400 mm versetzen',
      'Stöße nicht auf CW-Profil-Flansch',
      'Bei F90: GKF-Platten verwenden'
    ],
    crossTrade: 'Elektroinstallation muss vor Innenlage abgeschlossen sein',
    acoustic: { rating: 'Wichtig', notes: 'Erhöht Flächenmasse und damit Schalldämmung' },
    fire: { rating: 'F60-F90', notes: 'Kritisch für Feuerwiderstandsdauer. GKF-Platten für F90 erforderlich.' }
  },
  'mineral-wool': {
    name: 'Mineralwolle-Dämmung',
    shortName: 'MW 40',
    din: 'DIN EN 13162',
    category: ['acoustic', 'fire-protection'],
    material: {
      description: 'Steinwolle oder Glaswolle, Rohdichte 30-40 kg/m³',
      composition: 'Silikatfasern mit Bindemittel',
      dimensions: '40-80 mm Dicke, Plattenware oder Rollen'
    },
    function: 'Hohlraumdämpfung zur Verbesserung der Schalldämmung. Sekundär: Wärmedämmung und Brandschutz durch Hohlraumfüllung.',
    failureModes: [
      { type: 'Unvollständige Füllung', severity: 'high', description: 'Lücken und Hohlräume reduzieren Schalldämmung um bis zu 8 dB' },
      { type: 'Komprimierung', severity: 'medium', description: 'Zu starkes Zusammenpressen vermindert Dämmwirkung' },
      { type: 'Falsche Rohdichte', severity: 'medium', description: 'Zu leichte Wolle (< 25 kg/m³) hat geringere akustische Wirkung' }
    ],
    installation: [
      'Hohlraum vollständig ausfüllen, keine Lücken',
      'Matten leicht überdimensionieren (5-10 mm)',
      'Nicht komprimieren, locker einlegen',
      'Bei Installationsdurchführungen: Dämmung nachführen'
    ],
    crossTrade: 'Elektroinstallation vor Einbringung der Dämmung abschließen',
    acoustic: { rating: 'Entscheidend', notes: 'Verbesserung Rw um 4-8 dB gegenüber leerem Hohlraum. Optimum bei 40 kg/m³.' },
    fire: { rating: 'A1/A2', notes: 'Nicht brennbar. Schmelzpunkt > 1000°C. Verhindert Hohlraumbrand.' }
  },
  'acoustic-strip': {
    name: 'Trenn-/Dämmstreifen',
    shortName: 'PE 3 mm',
    din: 'DIN 4109',
    category: ['acoustic', 'fasteners'],
    material: {
      description: 'Geschlossenporiger PE-Schaum oder Bitumenfilz',
      composition: 'Polyethylen-Schaum, Dicke 3-5 mm',
      dimensions: 'Breite 50-95 mm (Profilbreite + 10 mm)'
    },
    function: 'Körperschallentkopplung zwischen Metallprofilen und angrenzenden Bauteilen. Verhindert direkte Schallübertragung.',
    failureModes: [
      { type: 'Fehlender Einbau', severity: 'critical', description: 'Häufigster Fehler! Ohne Trennstreifen: Schallschutzminderung 5-12 dB' },
      { type: 'Falsches Material', severity: 'medium', description: 'Offenporiger Schaum hat keine Entkopplungswirkung' },
      { type: 'Unterbrechungen', severity: 'high', description: 'Lücken im Streifen = punktuelle Schallbrücken' }
    ],
    installation: [
      'IMMER unter allen UW-Profilen verlegen',
      'Streifen überlappen, nicht stoßen',
      'Selbstklebende Ausführung bevorzugen',
      'Auch an Wandanschlüssen und Stützen'
    ],
    crossTrade: 'Trockenbauer ist verantwortlich – nicht dem Bodenleger überlassen',
    acoustic: { rating: 'KRITISCH', notes: 'Ohne Streifen ist Schallschutznachweis nicht zu führen!' },
    fire: { rating: 'B2', notes: 'Normal entflammbar, aber geringe Menge. Kein Einfluss auf Gesamtbrandschutz.' }
  },
  'sealing-tape': {
    name: 'Dichtungsband / Fugenband',
    shortName: 'Kompriband',
    din: 'DIN 18542',
    category: ['acoustic', 'moisture'],
    material: {
      description: 'Vorkomprimiertes Fugendichtband oder Acryl-Dichtstoff',
      composition: 'PU-Schaum imprägniert oder Acryl-Dispersionen',
      dimensions: '10-20 mm Breite, variable Dicke'
    },
    function: 'Luftdichte Abdichtung von Anschlussfugen. Verhindert Schallnebenwege und Zugluft. Wichtig für Schallschutz und Raumluftdichtheit.',
    failureModes: [
      { type: 'Fehlende Ausführung', severity: 'high', description: 'Offene Fugen = Schallnebenwege, Luftundichtigkeit' },
      { type: 'Falsches Produkt', severity: 'medium', description: 'Silikon statt Acryl führt zu Haftungsproblemen bei Überarbeitung' },
      { type: 'Unvollständige Fuge', severity: 'medium', description: 'Unterbrochene Abdichtung = punktuelle Schwachstellen' }
    ],
    installation: [
      'Fugen zwischen Platte und angrenzenden Bauteilen abdichten',
      'Bodenabstand 10 mm mit Acryl verfüllen',
      'Deckenanschluss luftdicht ausführen',
      'Kompriband: Vor Beplankung einlegen'
    ],
    crossTrade: 'Abstimmung mit Maler (überarbeitbar) und Luftdichtheitsprüfung',
    acoustic: { rating: 'Wichtig', notes: 'Dichte Fugen verhindern Schallnebenwege über Randanschlüsse' },
    fire: { rating: 'Variabel', notes: 'Brandschutz-Dichtmassen für F90-Wände erforderlich' }
  },
  'access-floor-tile': {
    name: 'Doppelboden-Platte',
    shortName: 'DB 600',
    din: 'DIN EN 12825',
    category: ['raised-floor'],
    material: {
      description: 'Calciumsulfat- oder Holzwerkstoff-Kernplatte mit Stahlblechummantelung',
      composition: 'Kern: Calciumsulfat (Gipsfaser) oder Spanplatte. Ummantelung: Stahlblech 0,5 mm',
      dimensions: '600 × 600 mm, Dicke 28-40 mm'
    },
    function: 'Begehbare Bodenplatte des Doppelbodensystems. Ermöglicht Unterflur-Installation von Elektro, IT und Klima. Trägt Nutzlasten.',
    failureModes: [
      { type: 'Plattenversatz', severity: 'low', description: 'Ungleichmäßige Auflage führt zu Kippeln und Geräuschen' },
      { type: 'Überlastung', severity: 'high', description: 'Punktlasten über Klassengrenze führen zu Plattenbruch' },
      { type: 'Feuchteschaden', severity: 'high', description: 'Calciumsulfat-Platten bei Wasserschaden irreparabel' }
    ],
    installation: [
      'Platten mit Saugheber verlegen',
      'Randplatten passgenau zuschneiden',
      'Fugenbild einheitlich ausrichten',
      'Belastungsklasse prüfen (mind. Klasse 3 für Büro)'
    ],
    crossTrade: 'KRITISCH: Doppelboden-Randabschluss an Trockenbauwand abstimmen. Bodenplatte NICHT unter UW-Profil führen!',
    acoustic: { rating: 'Systemabhängig', notes: 'Trittschall über Stützen in Rohboden. Entkopplung durch Elastomere.' },
    fire: { rating: 'A2-s1, d0', notes: 'Calciumsulfat-Platten nicht brennbar. Brandschutz unter Doppelboden beachten.' }
  },
  'access-floor-pedestal': {
    name: 'Doppelboden-Stütze',
    shortName: 'Stütze',
    din: 'DIN EN 12825',
    category: ['raised-floor', 'load-bearing'],
    material: {
      description: 'Höhenverstellbare Stahlstütze mit Kopfplatte',
      composition: 'Stahl verzinkt, Spindel M16/M20, Fußplatte mit Dübelbefestigung',
      dimensions: 'Höhe variabel 50-1500 mm, Kopfplatte 120 × 120 mm'
    },
    function: 'Trägt Doppelbodenplatten und leitet Lasten in den Rohboden ab. Höhenverstellung ermöglicht Niveauausgleich.',
    failureModes: [
      { type: 'Falscher Achsabstand', severity: 'high', description: 'Stützenabstand > 600 mm ohne Traversen = Durchbiegung' },
      { type: 'Fehlende Verklebung', severity: 'medium', description: 'Stützen müssen im Rohboden verklebt oder gedübelt sein' },
      { type: 'Korrosion', severity: 'medium', description: 'In Feuchträumen Edelstahlausführung erforderlich' }
    ],
    installation: [
      'Stützenraster 600 × 600 mm (Plattenmaß)',
      'Verklebung mit PU-Kleber oder Dübelbefestigung',
      'Höhenausgleich mit Wasserwaage oder Laser',
      'Randstützen ≤ 150 mm von Wand'
    ],
    crossTrade: 'Vor Trockenbau-Montage: Position der wandnahen Stützen festlegen',
    acoustic: { rating: 'Kritisch', notes: 'Stützen übertragen Körperschall. Elastomer-Unterlagen empfohlen.' },
    fire: { rating: 'A1', notes: 'Stahl nicht brennbar. Standsicherheit im Brandfall gewährleistet.' }
  },
  'access-floor-stringer': {
    name: 'Doppelboden-Traverse',
    shortName: 'Traverse',
    din: 'DIN EN 12825',
    category: ['raised-floor', 'load-bearing'],
    material: {
      description: 'Stahlprofil zur Plattenauflage zwischen Stützen',
      composition: 'Stahl verzinkt, Hutprofil oder Flachstahl',
      dimensions: '25-40 mm Höhe, Länge 600 mm'
    },
    function: 'Verbindet Stützenköpfe und bildet umlaufende Auflage für Bodenplatten. Erhöht Systemsteifigkeit.',
    failureModes: [
      { type: 'Fehlende Verlegung', severity: 'medium', description: 'Traversen bei hohen Lastklassen obligatorisch' },
      { type: 'Lose Verbindung', severity: 'low', description: 'Nicht eingerastete Traversen führen zu Geräuschen' }
    ],
    installation: [
      'Traversen in Stützenköpfe einclipsen oder verschrauben',
      'Vollflächige Auflage der Platten gewährleisten',
      'Bei Schallschutzanforderungen: Elastomer-Auflagestreifen'
    ],
    crossTrade: 'Elektro- und IT-Gewerke benötigen Aussparungen für Kabelführung',
    acoustic: { rating: 'Sekundär', notes: 'Elastomerstreifen auf Traversenoberseite reduziert Trittschall' },
    fire: { rating: 'A1', notes: 'Stahl nicht brennbar' }
  },
  'wall-floor-seal': {
    name: 'Wandanschluss-Abdichtung',
    shortName: 'Anschlussfuge',
    din: 'DIN 18540',
    category: ['moisture', 'acoustic'],
    material: {
      description: 'Dauerelastische Fugenmasse oder Anschlussband',
      composition: 'Acryl oder PU-Dichtstoff, ggf. mit Brandschutzklassifizierung',
      dimensions: 'Fugenbreite 5-15 mm'
    },
    function: 'Dauerelastische Abdichtung der Bewegungsfuge zwischen Trockenbauwand und Doppelboden. Kompensiert Toleranzen und Bewegungen.',
    failureModes: [
      { type: 'Starre Verfüllung', severity: 'high', description: 'Spachtel oder Mörtel führt zu Rissen bei Bewegung' },
      { type: 'Fehlende Ausführung', severity: 'medium', description: 'Offene Fuge = Schmutz, Schall, Zugluft' },
      { type: 'Falsches Material', severity: 'medium', description: 'Silikon nicht überstreichbar, Acryl bei Feuchtigkeit ungeeignet' }
    ],
    installation: [
      'Fugenbreite mind. 5 mm einhalten',
      'Hinterfüllung mit PE-Rundschnur bei tiefen Fugen',
      'Elastische Dichtstoffe verwenden',
      'Übergangsprofil oder Sockelleiste als Abdeckung'
    ],
    crossTrade: 'Maler: Anschlussfuge nicht überstreichen. Bodenleger: Toleranz zur Wand einhalten.',
    acoustic: { rating: 'Wichtig', notes: 'Luftdichte Fuge verhindert Schallnebenwege' },
    fire: { rating: 'Variabel', notes: 'Bei Brandwänden: Brandschutzkitt erforderlich' }
  },
  'fire-collar': {
    name: 'Brandschutzmanschette / -kitt',
    shortName: 'Brandschutz',
    din: 'DIN 4102-11',
    category: ['fire-protection'],
    material: {
      description: 'Intumeszierende Brandschutzmasse oder Manschette',
      composition: 'Expandierende Grafitverbindungen oder Brandschutzkitt',
      dimensions: 'Nach Durchführungsgröße'
    },
    function: 'Verschließt Durchführungen (Kabel, Rohre) durch brandschutzklassifizierte Bauteile. Verhindert Feuer- und Rauchausbreitung.',
    failureModes: [
      { type: 'Fehlender Einbau', severity: 'critical', description: 'Offene Durchführungen hebeln gesamten Brandschutz aus' },
      { type: 'Falsche Dimensionierung', severity: 'high', description: 'Unterdimensionierte Manschetten schließen nicht vollständig' },
      { type: 'Nachträgliche Beschädigung', severity: 'high', description: 'Kabelzug nach Abschottung ohne Nacharbeit' }
    ],
    installation: [
      'Abschottungen gem. Zulassung (AbP/aBG) ausführen',
      'Dokumentation jeder Abschottung (Abnahme)',
      'Nachträgliche Belegung nur mit Freigabe',
      'Kennzeichnung mit Prüfzeugnis und Datum'
    ],
    crossTrade: 'Elektro/Sanitär: Brandschutzbeauftragten vor Belegung informieren',
    acoustic: { rating: 'Sekundär', notes: 'Brandschutzkitt dient auch der akustischen Abdichtung' },
    fire: { rating: 'F30-F120', notes: 'KRITISCH: Abschottung muss Feuerwiderstand der Wand entsprechen!' }
  },
  'edge-profile': {
    name: 'Randprofil / Sockelblende',
    shortName: 'Randprofil',
    din: '-',
    category: ['raised-floor', 'finishing'],
    material: {
      description: 'Aluminium- oder Stahlprofil als Randabschluss',
      composition: 'Aluminium eloxiert oder Stahl pulverbeschichtet',
      dimensions: '30-50 mm Höhe, Längen variabel'
    },
    function: 'Optischer und funktionaler Abschluss des Doppelbodens an Wandanschlüssen. Verbirgt Schnittkanten und Fuge.',
    failureModes: [
      { type: 'Fehlmontage', severity: 'low', description: 'Sichtbare Befestigung oder Welligkeit' },
      { type: 'Falsche Höhe', severity: 'low', description: 'Profil steht über oder unter Bodenbelag' }
    ],
    installation: [
      'Montage nach Bodenbelagsverlegung',
      'Verdeckte Verschraubung bevorzugen',
      'Gehrungsschnitte an Ecken'
    ],
    crossTrade: 'Bodenleger / Innenausbau: Abstimmung mit Sockelleistendetail',
    acoustic: { rating: 'Keine', notes: 'Kein direkter Einfluss' },
    fire: { rating: 'A1', notes: 'Metall nicht brennbar' }
  }
};

// Layer category definitions
const LAYER_CATEGORIES = [
  { 
    id: 'all', 
    name: 'Alle Komponenten', 
    color: '#6B7280',
    description: 'Vollständige Ansicht aller Bauteile'
  },
  { 
    id: 'load-bearing', 
    name: 'Tragwerk', 
    color: '#1E3A5F',
    description: 'Lastabtragende Konstruktionselemente'
  },
  { 
    id: 'finishing', 
    name: 'Bekleidung', 
    color: '#8B7355',
    description: 'Oberflächenbildende Schichten'
  },
  { 
    id: 'acoustic', 
    name: 'Akustik', 
    color: '#4A6741',
    description: 'Schallschutztechnische Komponenten'
  },
  { 
    id: 'fire-protection', 
    name: 'Brandschutz', 
    color: '#8B2500',
    description: 'Feuerwiderstand & Abschottung'
  },
  { 
    id: 'moisture', 
    name: 'Abdichtung', 
    color: '#4A708B',
    description: 'Luft- und Feuchtigkeitssperre'
  },
  { 
    id: 'raised-floor', 
    name: 'Doppelboden', 
    color: '#5D478B',
    description: 'Hohlboden-Systemkomponenten'
  },
  { 
    id: 'fasteners', 
    name: 'Verbinder', 
    color: '#555555',
    description: 'Befestigungen & Anschlüsse'
  }
];

// Failure modes for inspector
const FAILURE_SCENARIOS = [
  {
    id: 'sound-bridge',
    name: 'Schallbrücke',
    description: 'Körperschallübertragung durch direkten Kontakt',
    affectedComponents: ['uw-profile-bottom', 'acoustic-strip'],
    severity: 'critical',
    indicator: 'Fehlender Trennstreifen unter UW-Profil'
  },
  {
    id: 'missing-seal',
    name: 'Fehlende Abdichtung',
    description: 'Luftundichtigkeit an Anschlussfugen',
    affectedComponents: ['sealing-tape', 'wall-floor-seal'],
    severity: 'high',
    indicator: 'Offene Fuge zwischen Wand und Boden'
  },
  {
    id: 'pedestal-spacing',
    name: 'Stützenabstand falsch',
    description: 'Zu große Stützenabstände führen zu Durchbiegung',
    affectedComponents: ['access-floor-pedestal'],
    severity: 'medium',
    indicator: 'Stützenraster > 600 mm'
  },
  {
    id: 'screw-spacing',
    name: 'Schraubenabstand',
    description: 'Falsche Befestigungsabstände der Beplankung',
    affectedComponents: ['gypsum-board-outer', 'gypsum-board-inner'],
    severity: 'medium',
    indicator: 'Schraubenabstand Rand > 150 mm'
  },
  {
    id: 'missing-insulation',
    name: 'Dämmung fehlt',
    description: 'Unvollständige Hohlraumdämmung',
    affectedComponents: ['mineral-wool'],
    severity: 'high',
    indicator: 'Lücken oder Fehlstellen in Mineralwolle'
  },
  {
    id: 'fire-breach',
    name: 'Brandschutzlücke',
    description: 'Nicht abgeschottete Durchführung',
    affectedComponents: ['fire-collar', 'gypsum-board-inner'],
    severity: 'critical',
    indicator: 'Kabeldurchführung ohne Brandschott'
  }
];

// Zoom hotspots
const ZOOM_HOTSPOTS = [
  {
    id: 'bottom-track',
    name: 'Fußpunktdetail',
    description: 'UW-Profil auf Rohboden mit Trennstreifen',
    bounds: { x: 80, y: 320, width: 200, height: 100 }
  },
  {
    id: 'pedestal-head',
    name: 'Stützenkopf',
    description: 'Traverse-Auflage auf Doppelbodenstütze',
    bounds: { x: 280, y: 280, width: 140, height: 80 }
  },
  {
    id: 'wall-floor-joint',
    name: 'Anschlussfuge',
    description: 'Übergang Trockenbauwand zu Doppelboden',
    bounds: { x: 180, y: 200, width: 160, height: 120 }
  },
  {
    id: 'profile-connection',
    name: 'Profilverbindung',
    description: 'CW in UW eingestellt',
    bounds: { x: 100, y: 160, width: 100, height: 80 }
  }
];

// Technical SVG of the construction detail
const TechnicalSVG = ({ 
  activeComponent, 
  setActiveComponent, 
  activeCategory, 
  failureMode,
  zoomLevel,
  panOffset,
  onHover,
  onClick
}) => {
  const getComponentOpacity = (componentId) => {
    if (activeCategory === 'all') return 1;
    const component = COMPONENT_DATA[componentId];
    if (!component) return 0.15;
    return component.category.includes(activeCategory) ? 1 : 0.15;
  };

  const getFailureHighlight = (componentId) => {
    if (!failureMode) return null;
    const scenario = FAILURE_SCENARIOS.find(f => f.id === failureMode);
    if (scenario && scenario.affectedComponents.includes(componentId)) {
      return scenario.severity === 'critical' ? '#B22222' : 
             scenario.severity === 'high' ? '#CD5C5C' : '#DAA520';
    }
    return null;
  };

  const handleMouseEnter = (componentId) => {
    if (COMPONENT_DATA[componentId]) {
      setActiveComponent(componentId);
      if (onHover) onHover(componentId);
    }
  };

  const handleMouseLeave = () => {
    // Keep component active for click interactions
  };

  const handleClick = (componentId, e) => {
    e.stopPropagation();
    if (COMPONENT_DATA[componentId] && onClick) {
      onClick(componentId);
    }
  };

  const baseStroke = '#3D3D3D';
  const highlightStroke = '#1E3A5F';
  
  return (
    <svg 
      viewBox="0 0 500 450" 
      className="w-full h-full"
      style={{ 
        transform: `scale(${zoomLevel}) translate(${panOffset.x}px, ${panOffset.y}px)`,
        transformOrigin: 'center center'
      }}
    >
      {/* Background grid - subtle technical drawing style */}
      <defs>
        <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M 20 0 L 0 0 0 20" fill="none" stroke="#E8E4DF" strokeWidth="0.3"/>
        </pattern>
        <pattern id="gridMajor" width="100" height="100" patternUnits="userSpaceOnUse">
          <path d="M 100 0 L 0 0 0 100" fill="none" stroke="#D4CFC8" strokeWidth="0.5"/>
        </pattern>
        
        {/* Hatching patterns */}
        <pattern id="concreteHatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="8" stroke="#9CA3AF" strokeWidth="0.5"/>
        </pattern>
        <pattern id="insulationHatch" width="6" height="6" patternUnits="userSpaceOnUse">
          <circle cx="3" cy="3" r="1.5" fill="none" stroke="#6B8E23" strokeWidth="0.3"/>
        </pattern>
        <pattern id="gypsumHatch" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(-30)">
          <line x1="0" y1="0" x2="10" y2="0" stroke="#A0A0A0" strokeWidth="0.3"/>
        </pattern>
        
        {/* Shadow filter */}
        <filter id="componentShadow" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="1" dy="1" stdDeviation="1.5" floodOpacity="0.2"/>
        </filter>
        
        {/* Highlight glow */}
        <filter id="highlightGlow">
          <feGaussianBlur stdDeviation="2" result="blur"/>
          <feMerge>
            <feMergeNode in="blur"/>
            <feMergeNode in="SourceGraphic"/>
          </feMerge>
        </filter>
      </defs>
      
      {/* Grid background */}
      <rect width="500" height="450" fill="url(#grid)"/>
      <rect width="500" height="450" fill="url(#gridMajor)"/>
      
      {/* === ROHBODEN (Raw Floor) === */}
      <g id="raw-floor">
        <rect x="0" y="380" width="500" height="70" fill="url(#concreteHatch)" stroke={baseStroke} strokeWidth="1"/>
        <text x="450" y="420" className="text-[8px]" fill="#666" fontFamily="serif" fontStyle="italic">Rohboden</text>
      </g>
      
      {/* === DOPPELBODEN SYSTEM === */}
      <g id="raised-floor-system">
        {/* Pedestals */}
        <g 
          id="access-floor-pedestal"
          opacity={getComponentOpacity('access-floor-pedestal')}
          onMouseEnter={() => handleMouseEnter('access-floor-pedestal')}
          onMouseLeave={handleMouseLeave}
          onClick={(e) => handleClick('access-floor-pedestal', e)}
          style={{ cursor: 'pointer' }}
          filter={activeComponent === 'access-floor-pedestal' ? 'url(#componentShadow)' : undefined}
        >
          {/* Pedestal 1 */}
          <rect 
            x="295" y="380" width="30" height="8" 
            fill={getFailureHighlight('access-floor-pedestal') || '#505050'} 
            stroke={activeComponent === 'access-floor-pedestal' ? highlightStroke : baseStroke} 
            strokeWidth={activeComponent === 'access-floor-pedestal' ? 2 : 1}
          />
          <rect x="305" y="305" width="10" height="75" fill="#606060" stroke={baseStroke} strokeWidth="0.5"/>
          <rect 
            x="290" y="295" width="40" height="12" 
            fill="#707070" 
            stroke={activeComponent === 'access-floor-pedestal' ? highlightStroke : baseStroke}
            strokeWidth={activeComponent === 'access-floor-pedestal' ? 2 : 1}
          />
          
          {/* Pedestal 2 */}
          <rect x="395" y="380" width="30" height="8" fill="#505050" stroke={baseStroke} strokeWidth="1"/>
          <rect x="405" y="305" width="10" height="75" fill="#606060" stroke={baseStroke} strokeWidth="0.5"/>
          <rect x="390" y="295" width="40" height="12" fill="#707070" stroke={baseStroke} strokeWidth="1"/>
        </g>
        
        {/* Stringers/Traverses */}
        <g 
          id="access-floor-stringer"
          opacity={getComponentOpacity('access-floor-stringer')}
          onMouseEnter={() => handleMouseEnter('access-floor-stringer')}
          onMouseLeave={handleMouseLeave}
          onClick={(e) => handleClick('access-floor-stringer', e)}
          style={{ cursor: 'pointer' }}
        >
          <rect 
            x="328" y="297" width="64" height="8" 
            fill={getFailureHighlight('access-floor-stringer') || '#787878'}
            stroke={activeComponent === 'access-floor-stringer' ? highlightStroke : baseStroke}
            strokeWidth={activeComponent === 'access-floor-stringer' ? 2 : 1}
          />
          <rect x="230" y="297" width="62" height="8" fill="#787878" stroke={baseStroke} strokeWidth="1"/>
        </g>
        
        {/* Access Floor Tiles */}
        <g 
          id="access-floor-tile"
          opacity={getComponentOpacity('access-floor-tile')}
          onMouseEnter={() => handleMouseEnter('access-floor-tile')}
          onMouseLeave={handleMouseLeave}
          onClick={(e) => handleClick('access-floor-tile', e)}
          style={{ cursor: 'pointer' }}
          filter={activeComponent === 'access-floor-tile' ? 'url(#componentShadow)' : undefined}
        >
          <rect 
            x="230" y="265" width="100" height="32" 
            fill={getFailureHighlight('access-floor-tile') || '#B8A88A'}
            stroke={activeComponent === 'access-floor-tile' ? highlightStroke : baseStroke}
            strokeWidth={activeComponent === 'access-floor-tile' ? 2 : 1}
          />
          <line x1="230" y1="268" x2="330" y2="268" stroke="#8B7355" strokeWidth="0.5"/>
          <line x1="230" y1="294" x2="330" y2="294" stroke="#8B7355" strokeWidth="0.5"/>
          
          <rect x="332" y="265" width="100" height="32" fill="#B8A88A" stroke={baseStroke} strokeWidth="1"/>
          <line x1="332" y1="268" x2="432" y2="268" stroke="#8B7355" strokeWidth="0.5"/>
          <line x1="332" y1="294" x2="432" y2="294" stroke="#8B7355" strokeWidth="0.5"/>
          
          {/* Floor covering */}
          <rect x="230" y="258" width="202" height="8" fill="#C4B896" stroke={baseStroke} strokeWidth="0.5"/>
          <text x="420" y="250" className="text-[7px]" fill="#666" fontFamily="serif" fontStyle="italic">Bodenbelag</text>
        </g>
        
        {/* Edge Profile */}
        <g 
          id="edge-profile"
          opacity={getComponentOpacity('edge-profile')}
          onMouseEnter={() => handleMouseEnter('edge-profile')}
          onMouseLeave={handleMouseLeave}
          onClick={(e) => handleClick('edge-profile', e)}
          style={{ cursor: 'pointer' }}
        >
          <path 
            d="M 218 258 L 218 250 L 228 250 L 228 265 L 218 265 Z" 
            fill={getFailureHighlight('edge-profile') || '#909090'}
            stroke={activeComponent === 'edge-profile' ? highlightStroke : baseStroke}
            strokeWidth={activeComponent === 'edge-profile' ? 2 : 1}
          />
        </g>
      </g>
      
      {/* === TROCKENBAUWAND (Drywall Partition) === */}
      <g id="drywall-partition">
        
        {/* Bottom UW Profile with Acoustic Strip */}
        <g 
          id="acoustic-strip"
          opacity={getComponentOpacity('acoustic-strip')}
          onMouseEnter={() => handleMouseEnter('acoustic-strip')}
          onMouseLeave={handleMouseLeave}
          onClick={(e) => handleClick('acoustic-strip', e)}
          style={{ cursor: 'pointer' }}
        >
          <rect 
            x="88" y="376" width="82" height="4" 
            fill={getFailureHighlight('acoustic-strip') || '#2F4F4F'}
            stroke={activeComponent === 'acoustic-strip' ? highlightStroke : '#1C3030'}
            strokeWidth={activeComponent === 'acoustic-strip' ? 2 : 1}
          />
        </g>
        
        <g 
          id="uw-profile-bottom"
          opacity={getComponentOpacity('uw-profile-bottom')}
          onMouseEnter={() => handleMouseEnter('uw-profile-bottom')}
          onMouseLeave={handleMouseLeave}
          onClick={(e) => handleClick('uw-profile-bottom', e)}
          style={{ cursor: 'pointer' }}
          filter={activeComponent === 'uw-profile-bottom' ? 'url(#componentShadow)' : undefined}
        >
          <path 
            d="M 90 376 L 90 340 L 95 340 L 95 371 L 165 371 L 165 340 L 170 340 L 170 376 Z" 
            fill={getFailureHighlight('uw-profile-bottom') || '#A8A8A8'}
            stroke={activeComponent === 'uw-profile-bottom' ? highlightStroke : baseStroke}
            strokeWidth={activeComponent === 'uw-profile-bottom' ? 2 : 1}
          />
          {/* Screw symbols */}
          <circle cx="100" cy="378" r="2" fill="#333" stroke="#222" strokeWidth="0.5"/>
          <circle cx="160" cy="378" r="2" fill="#333" stroke="#222" strokeWidth="0.5"/>
        </g>
        
        {/* CW Profiles */}
        <g 
          id="cw-profile"
          opacity={getComponentOpacity('cw-profile')}
          onMouseEnter={() => handleMouseEnter('cw-profile')}
          onMouseLeave={handleMouseLeave}
          onClick={(e) => handleClick('cw-profile', e)}
          style={{ cursor: 'pointer' }}
          filter={activeComponent === 'cw-profile' ? 'url(#componentShadow)' : undefined}
        >
          {/* CW Profile 1 */}
          <path 
            d="M 98 340 L 98 80 L 103 80 L 103 85 L 157 85 L 157 80 L 162 80 L 162 340 L 157 340 L 157 95 L 103 95 L 103 340 Z" 
            fill={getFailureHighlight('cw-profile') || '#B0B0B0'}
            stroke={activeComponent === 'cw-profile' ? highlightStroke : baseStroke}
            strokeWidth={activeComponent === 'cw-profile' ? 2 : 1}
          />
          {/* H-Stanzungen (service holes) */}
          <ellipse cx="130" cy="180" rx="15" ry="6" fill="none" stroke="#888" strokeWidth="0.5" strokeDasharray="2,1"/>
          <ellipse cx="130" cy="280" rx="15" ry="6" fill="none" stroke="#888" strokeWidth="0.5" strokeDasharray="2,1"/>
        </g>
        
        {/* UA Profile (reinforcement) */}
        <g 
          id="ua-profile"
          opacity={getComponentOpacity('ua-profile')}
          onMouseEnter={() => handleMouseEnter('ua-profile')}
          onMouseLeave={handleMouseLeave}
          onClick={(e) => handleClick('ua-profile', e)}
          style={{ cursor: 'pointer' }}
        >
          <rect 
            x="175" y="80" width="8" height="290" 
            fill={getFailureHighlight('ua-profile') || '#909090'}
            stroke={activeComponent === 'ua-profile' ? highlightStroke : baseStroke}
            strokeWidth={activeComponent === 'ua-profile' ? 2 : 1}
          />
          {/* UA bracket symbols */}
          <path d="M 175 85 L 185 85 L 190 75 L 195 75" fill="none" stroke="#666" strokeWidth="1"/>
          <path d="M 175 365 L 185 365 L 190 375 L 195 375" fill="none" stroke="#666" strokeWidth="1"/>
        </g>
        
        {/* Top UW Profile */}
        <g 
          id="uw-profile-top"
          opacity={getComponentOpacity('uw-profile-top')}
          onMouseEnter={() => handleMouseEnter('uw-profile-top')}
          onMouseLeave={handleMouseLeave}
          onClick={(e) => handleClick('uw-profile-top', e)}
          style={{ cursor: 'pointer' }}
        >
          <path 
            d="M 90 80 L 90 45 L 95 45 L 95 75 L 165 75 L 165 45 L 170 45 L 170 80 Z" 
            fill={getFailureHighlight('uw-profile-top') || '#A8A8A8'}
            stroke={activeComponent === 'uw-profile-top' ? highlightStroke : baseStroke}
            strokeWidth={activeComponent === 'uw-profile-top' ? 2 : 1}
          />
          {/* Acoustic strip on top */}
          <rect x="88" y="41" width="82" height="4" fill="#2F4F4F" stroke="#1C3030" strokeWidth="0.5"/>
        </g>
        
        {/* Mineral Wool Insulation */}
        <g 
          id="mineral-wool"
          opacity={getComponentOpacity('mineral-wool')}
          onMouseEnter={() => handleMouseEnter('mineral-wool')}
          onMouseLeave={handleMouseLeave}
          onClick={(e) => handleClick('mineral-wool', e)}
          style={{ cursor: 'pointer' }}
          filter={activeComponent === 'mineral-wool' ? 'url(#componentShadow)' : undefined}
        >
          <rect 
            x="103" y="95" width="54" height="245" 
            fill={getFailureHighlight('mineral-wool') || 'url(#insulationHatch)'}
            stroke={activeComponent === 'mineral-wool' ? highlightStroke : '#6B8E23'}
            strokeWidth={activeComponent === 'mineral-wool' ? 2 : 1}
          />
          {/* Texture lines for insulation */}
          <path d="M 108 120 Q 120 115 132 120 Q 145 125 152 120" fill="none" stroke="#8FBC8F" strokeWidth="0.5"/>
          <path d="M 108 160 Q 125 155 142 160 Q 150 165 152 160" fill="none" stroke="#8FBC8F" strokeWidth="0.5"/>
          <path d="M 108 200 Q 118 195 128 200 Q 140 205 152 200" fill="none" stroke="#8FBC8F" strokeWidth="0.5"/>
          <path d="M 108 240 Q 122 235 136 240 Q 148 245 152 240" fill="none" stroke="#8FBC8F" strokeWidth="0.5"/>
          <path d="M 108 280 Q 115 275 125 280 Q 138 285 152 280" fill="none" stroke="#8FBC8F" strokeWidth="0.5"/>
          <path d="M 108 320 Q 128 315 148 320" fill="none" stroke="#8FBC8F" strokeWidth="0.5"/>
        </g>
        
        {/* Inner Gypsum Board (Layer 1) */}
        <g 
          id="gypsum-board-inner"
          opacity={getComponentOpacity('gypsum-board-inner')}
          onMouseEnter={() => handleMouseEnter('gypsum-board-inner')}
          onMouseLeave={handleMouseLeave}
          onClick={(e) => handleClick('gypsum-board-inner', e)}
          style={{ cursor: 'pointer' }}
        >
          {/* Left side */}
          <rect 
            x="78" y="55" width="12" height="310" 
            fill={getFailureHighlight('gypsum-board-inner') || '#E8DFD0'}
            stroke={activeComponent === 'gypsum-board-inner' ? highlightStroke : '#B8A88A'}
            strokeWidth={activeComponent === 'gypsum-board-inner' ? 2 : 1}
          />
          {/* Right side */}
          <rect 
            x="170" y="55" width="12" height="310" 
            fill={getFailureHighlight('gypsum-board-inner') || '#E8DFD0'}
            stroke={activeComponent === 'gypsum-board-inner' ? highlightStroke : '#B8A88A'}
            strokeWidth={activeComponent === 'gypsum-board-inner' ? 2 : 1}
          />
        </g>
        
        {/* Outer Gypsum Board (Layer 2) */}
        <g 
          id="gypsum-board-outer"
          opacity={getComponentOpacity('gypsum-board-outer')}
          onMouseEnter={() => handleMouseEnter('gypsum-board-outer')}
          onMouseLeave={handleMouseLeave}
          onClick={(e) => handleClick('gypsum-board-outer', e)}
          style={{ cursor: 'pointer' }}
          filter={activeComponent === 'gypsum-board-outer' ? 'url(#componentShadow)' : undefined}
        >
          {/* Left side */}
          <rect 
            x="65" y="50" width="13" height="315" 
            fill={getFailureHighlight('gypsum-board-outer') || '#F5F0E6'}
            stroke={activeComponent === 'gypsum-board-outer' ? highlightStroke : '#C4B896'}
            strokeWidth={activeComponent === 'gypsum-board-outer' ? 2 : 1}
          />
          {/* Screw pattern */}
          <circle cx="72" cy="70" r="1" fill="#666"/>
          <circle cx="72" cy="120" r="1" fill="#666"/>
          <circle cx="72" cy="170" r="1" fill="#666"/>
          <circle cx="72" cy="220" r="1" fill="#666"/>
          <circle cx="72" cy="270" r="1" fill="#666"/>
          <circle cx="72" cy="320" r="1" fill="#666"/>
          <circle cx="72" cy="355" r="1" fill="#666"/>
          
          {/* Right side */}
          <rect 
            x="182" y="50" width="13" height="212" 
            fill={getFailureHighlight('gypsum-board-outer') || '#F5F0E6'}
            stroke={activeComponent === 'gypsum-board-outer' ? highlightStroke : '#C4B896'}
            strokeWidth={activeComponent === 'gypsum-board-outer' ? 2 : 1}
          />
          <circle cx="189" cy="70" r="1" fill="#666"/>
          <circle cx="189" cy="120" r="1" fill="#666"/>
          <circle cx="189" cy="170" r="1" fill="#666"/>
          <circle cx="189" cy="220" r="1" fill="#666"/>
        </g>
        
        {/* Sealing Tape at bottom */}
        <g 
          id="sealing-tape"
          opacity={getComponentOpacity('sealing-tape')}
          onMouseEnter={() => handleMouseEnter('sealing-tape')}
          onMouseLeave={handleMouseLeave}
          onClick={(e) => handleClick('sealing-tape', e)}
          style={{ cursor: 'pointer' }}
        >
          <rect 
            x="65" y="365" width="13" height="6" 
            fill={getFailureHighlight('sealing-tape') || '#4682B4'}
            stroke={activeComponent === 'sealing-tape' ? highlightStroke : '#2F4F4F'}
            strokeWidth={activeComponent === 'sealing-tape' ? 2 : 1}
          />
          <rect x="182" y="262" width="13" height="6" fill="#4682B4" stroke="#2F4F4F" strokeWidth="0.5"/>
        </g>
        
        {/* Wall-Floor Seal */}
        <g 
          id="wall-floor-seal"
          opacity={getComponentOpacity('wall-floor-seal')}
          onMouseEnter={() => handleMouseEnter('wall-floor-seal')}
          onMouseLeave={handleMouseLeave}
          onClick={(e) => handleClick('wall-floor-seal', e)}
          style={{ cursor: 'pointer' }}
        >
          <path 
            d="M 195 262 Q 205 260 215 262 L 215 268 Q 205 266 195 268 Z" 
            fill={getFailureHighlight('wall-floor-seal') || '#708090'}
            stroke={activeComponent === 'wall-floor-seal' ? highlightStroke : '#4A5568'}
            strokeWidth={activeComponent === 'wall-floor-seal' ? 2 : 1}
          />
        </g>
        
        {/* Fire Protection Detail */}
        <g 
          id="fire-collar"
          opacity={getComponentOpacity('fire-collar')}
          onMouseEnter={() => handleMouseEnter('fire-collar')}
          onMouseLeave={handleMouseLeave}
          onClick={(e) => handleClick('fire-collar', e)}
          style={{ cursor: 'pointer' }}
        >
          {/* Cable penetration with fire collar */}
          <ellipse cx="130" cy="180" rx="8" ry="4" fill="none" stroke={getFailureHighlight('fire-collar') || '#CD5C5C'} strokeWidth="2"/>
          <ellipse 
            cx="130" cy="180" rx="12" ry="6" 
            fill="none" 
            stroke={activeComponent === 'fire-collar' ? highlightStroke : '#8B0000'}
            strokeWidth={activeComponent === 'fire-collar' ? 2 : 1}
            strokeDasharray="3,2"
          />
          <text x="145" y="178" className="text-[6px]" fill="#8B0000" fontFamily="serif">S90</text>
        </g>
      </g>
      
      {/* === DIMENSION LINES === */}
      <g id="dimensions" fill="none" stroke="#666" strokeWidth="0.5">
        {/* Wall thickness */}
        <line x1="55" y1="200" x2="55" y2="50"/>
        <line x1="50" y1="50" x2="60" y2="50"/>
        <line x1="50" y1="200" x2="60" y2="200"/>
        <text x="35" y="130" className="text-[7px]" fill="#666" fontFamily="sans-serif" transform="rotate(-90, 35, 130)">125 mm</text>
        
        {/* Floor height */}
        <line x1="450" y1="258" x2="450" y2="380"/>
        <line x1="445" y1="258" x2="455" y2="258"/>
        <line x1="445" y1="380" x2="455" y2="380"/>
        <text x="460" y="320" className="text-[7px]" fill="#666" fontFamily="sans-serif">122 mm</text>
        
        {/* Stud spacing */}
        <line x1="130" y1="30" x2="130" y2="40"/>
        <line x1="130" y1="35" x2="220" y2="35" strokeDasharray="4,2"/>
        <text x="165" y="28" className="text-[7px]" fill="#666" fontFamily="sans-serif">e = 625 mm</text>
      </g>
      
      {/* === LABELS === */}
      <g id="labels" fontFamily="Georgia, serif" fontSize="9" fill="#4A4A4A">
        <text x="10" y="25" fontWeight="bold" fontSize="11">Schnitt A-A</text>
        <text x="10" y="38" fontSize="8" fontStyle="italic">Trockenbauwand / Doppelboden-Anschluss</text>
        
        {/* Component labels with leader lines */}
        <g className="labels-detailed" fontSize="7" fill="#555">
          <line x1="40" y1="120" x2="63" y2="120" stroke="#888" strokeWidth="0.3"/>
          <text x="10" y="122">2× GK 12,5</text>
          
          <line x1="40" y1="200" x2="78" y2="200" stroke="#888" strokeWidth="0.3"/>
          <text x="10" y="202">MW 40 mm</text>
          
          <line x1="40" y1="355" x2="90" y2="355" stroke="#888" strokeWidth="0.3"/>
          <text x="10" y="357">UW 75</text>
        </g>
      </g>
      
      {/* Scale bar */}
      <g id="scale" transform="translate(350, 430)">
        <rect x="0" y="0" width="50" height="4" fill="#333"/>
        <rect x="50" y="0" width="50" height="4" fill="none" stroke="#333" strokeWidth="1"/>
        <text x="0" y="12" className="text-[6px]" fill="#666" fontFamily="sans-serif">0</text>
        <text x="45" y="12" className="text-[6px]" fill="#666" fontFamily="sans-serif">50</text>
        <text x="90" y="12" className="text-[6px]" fill="#666" fontFamily="sans-serif">100 mm</text>
      </g>
    </svg>
  );
};

// Tooltip Component
const Tooltip = ({ component, position }) => {
  if (!component || !COMPONENT_DATA[component]) return null;
  
  const data = COMPONENT_DATA[component];
  
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

// Info Panel Component
const InfoPanel = ({ componentId, onClose }) => {
  const data = COMPONENT_DATA[componentId];
  
  if (!data) {
    return (
      <div className="h-full flex items-center justify-center text-stone-500 font-serif italic px-6 text-center">
        Wählen Sie ein Bauteil aus der Zeichnung, um technische Informationen anzuzeigen.
      </div>
    );
  }
  
  const severityColors = {
    critical: 'bg-red-900/30 border-red-800 text-red-200',
    high: 'bg-orange-900/30 border-orange-800 text-orange-200',
    medium: 'bg-yellow-900/30 border-yellow-800 text-yellow-200',
    low: 'bg-stone-700/30 border-stone-600 text-stone-300'
  };
  
  return (
    <div className="h-full overflow-y-auto custom-scrollbar">
      {/* Header */}
      <div className="sticky top-0 bg-stone-900 border-b border-stone-700 px-4 py-3 z-10">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="font-serif text-lg text-stone-100">{data.name}</h2>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-xs font-mono text-stone-400">{data.shortName}</span>
              <span className="text-stone-600">•</span>
              <span className="text-xs text-stone-500">{data.din}</span>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="text-stone-500 hover:text-stone-300 transition-colors p-1"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>
      </div>
      
      <div className="px-4 py-4 space-y-5">
        {/* Material */}
        <section>
          <h3 className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">Material</h3>
          <div className="bg-stone-800/50 rounded p-3 space-y-2">
            <p className="text-sm text-stone-200">{data.material.description}</p>
            <p className="text-xs text-stone-400">{data.material.composition}</p>
            <p className="text-xs text-stone-500 font-mono">{data.material.dimensions}</p>
          </div>
        </section>
        
        {/* Function */}
        <section>
          <h3 className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">Funktion</h3>
          <p className="text-sm text-stone-300 leading-relaxed">{data.function}</p>
        </section>
        
        {/* Performance */}
        <section>
          <h3 className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">Leistungswerte</h3>
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-stone-800/50 rounded p-2">
              <div className="text-[10px] text-stone-500 uppercase">Akustik</div>
              <div className="text-xs font-semibold text-stone-200 mt-0.5">{data.acoustic.rating}</div>
              <div className="text-[10px] text-stone-400 mt-1">{data.acoustic.notes}</div>
            </div>
            <div className="bg-stone-800/50 rounded p-2">
              <div className="text-[10px] text-stone-500 uppercase">Brandschutz</div>
              <div className="text-xs font-semibold text-stone-200 mt-0.5">{data.fire.rating}</div>
              <div className="text-[10px] text-stone-400 mt-1">{data.fire.notes}</div>
            </div>
          </div>
        </section>
        
        {/* Failure Modes */}
        <section>
          <h3 className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">Typische Fehler</h3>
          <div className="space-y-2">
            {data.failureModes.map((failure, idx) => (
              <div 
                key={idx} 
                className={`rounded p-2 border ${severityColors[failure.severity]}`}
              >
                <div className="text-xs font-semibold">{failure.type}</div>
                <div className="text-[11px] mt-1 opacity-90">{failure.description}</div>
              </div>
            ))}
          </div>
        </section>
        
        {/* Installation Notes */}
        <section>
          <h3 className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">Einbauhinweise</h3>
          <ul className="space-y-1.5">
            {data.installation.map((note, idx) => (
              <li key={idx} className="text-sm text-stone-300 flex items-start gap-2">
                <span className="text-stone-600 mt-1">›</span>
                <span>{note}</span>
              </li>
            ))}
          </ul>
        </section>
        
        {/* Cross-Trade */}
        <section>
          <h3 className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">Gewerkekoordination</h3>
          <div className="bg-amber-900/20 border border-amber-800/50 rounded p-3">
            <p className="text-sm text-amber-200/90">{data.crossTrade}</p>
          </div>
        </section>
      </div>
    </div>
  );
};

// Layer Filter Panel
const LayerPanel = ({ activeCategory, setActiveCategory, failureMode, setFailureMode, onButtonClick }) => {
  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="px-4 py-3 border-b border-stone-700">
        <h2 className="font-serif text-sm text-stone-200">Ebenenfilter</h2>
      </div>
      
      {/* Category Filters */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-3 py-3">
        <div className="space-y-1">
          {LAYER_CATEGORIES.map(category => (
            <button
              key={category.id}
              onClick={() => {
                setActiveCategory(category.id);
                if (onButtonClick) onButtonClick();
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
        <div className="my-4 border-t border-stone-700"/>
        
        {/* Failure Inspector */}
        <div className="px-1">
          <h3 className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-2">
            Fehlerinspektor
          </h3>
          <div className="space-y-1">
            <button
              onClick={() => {
                setFailureMode(null);
                if (onButtonClick) onButtonClick();
              }}
              className={`w-full text-left px-3 py-2 rounded text-xs transition-all ${
                !failureMode 
                  ? 'bg-stone-700 text-stone-200' 
                  : 'text-stone-500 hover:bg-stone-800'
              }`}
            >
              Keine Fehler anzeigen
            </button>
            {FAILURE_SCENARIOS.map(scenario => (
              <button
                key={scenario.id}
                onClick={() => {
                  setFailureMode(failureMode === scenario.id ? null : scenario.id);
                  if (onButtonClick) onButtonClick();
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
                  }`}/>
                  <span className="text-xs">{scenario.name}</span>
                </div>
                {failureMode === scenario.id && (
                  <p className="text-[10px] opacity-75 mt-1 ml-4">{scenario.indicator}</p>
                )}
              </button>
            ))}
          </div>
        </div>
        
        {/* Divider */}
        <div className="my-4 border-t border-stone-700"/>
        
        {/* Zoom Hotspots */}
        <div className="px-1">
          <h3 className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-2">
            Detailansichten
          </h3>
          <div className="space-y-1">
            {ZOOM_HOTSPOTS.map(hotspot => (
              <button
                key={hotspot.id}
                onClick={() => {
                  if (onButtonClick) onButtonClick();
                }}
                className="w-full text-left px-3 py-2 rounded text-stone-500 hover:bg-stone-800 hover:text-stone-400 transition-all"
              >
                <div className="text-xs">{hotspot.name}</div>
                <div className="text-[10px] text-stone-600">{hotspot.description}</div>
              </button>
            ))}
          </div>
        </div>
      </div>
      
      {/* Footer */}
      <div className="px-4 py-3 border-t border-stone-700 bg-stone-900/50">
        <div className="text-[10px] text-stone-600 text-center">
          Scroll zum Zoomen • Klick für Details
        </div>
      </div>
    </div>
  );
};

// Main Application Component
export default function ConstructionDetailExplorer() {
  const [activeComponent, setActiveComponent] = useState(null);
  const [selectedComponent, setSelectedComponent] = useState(null);
  const [activeCategory, setActiveCategory] = useState('all');
  const [failureMode, setFailureMode] = useState(null);
  const [zoomLevel, setZoomLevel] = useState(1);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [tooltipPosition, setTooltipPosition] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState({ x: 0, y: 0 });
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [lastHoveredComponent, setLastHoveredComponent] = useState(null);
  
  const svgContainerRef = useRef(null);
  const { playHoverSound, playClickSound, playSelectSound, playErrorSound } = useSoundEffects();
  
  // Handle component hover with sound
  const handleComponentHover = useCallback((componentId) => {
    if (soundEnabled && componentId !== lastHoveredComponent) {
      playHoverSound();
      setLastHoveredComponent(componentId);
    }
  }, [soundEnabled, lastHoveredComponent, playHoverSound]);
  
  // Handle component click with sound
  const handleComponentClick = useCallback((componentId) => {
    if (soundEnabled) {
      playSelectSound();
    }
    setSelectedComponent(componentId);
  }, [soundEnabled, playSelectSound]);
  
  // Handle mouse move for tooltip
  const handleMouseMove = useCallback((e) => {
    if (svgContainerRef.current) {
      const rect = svgContainerRef.current.getBoundingClientRect();
      setTooltipPosition({
        x: e.clientX - rect.left,
        y: e.clientY - rect.top
      });
    }
    
    if (isPanning) {
      setPanOffset({
        x: (e.clientX - panStart.x) / zoomLevel,
        y: (e.clientY - panStart.y) / zoomLevel
      });
    }
  }, [isPanning, panStart, zoomLevel]);
  
  // Handle wheel for zoom
  const handleWheel = useCallback((e) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.1 : 0.1;
    setZoomLevel(prev => Math.min(Math.max(prev + delta, 0.5), 3));
  }, []);
  
  // Handle click on SVG background (deselect)
  const handleSVGClick = useCallback((e) => {
    // Only deselect if clicking on background, not on components
    if (e.target.tagName === 'svg' || e.target.id === 'grid' || e.target.tagName === 'rect') {
      if (soundEnabled) {
        playClickSound();
      }
    }
  }, [soundEnabled, playClickSound]);
  
  // Handle pan
  const handleMouseDown = useCallback((e) => {
    if (e.button === 1 || (e.button === 0 && e.shiftKey)) {
      setIsPanning(true);
      setPanStart({ x: e.clientX - panOffset.x * zoomLevel, y: e.clientY - panOffset.y * zoomLevel });
    }
  }, [panOffset, zoomLevel]);
  
  const handleMouseUp = useCallback(() => {
    setIsPanning(false);
  }, []);
  
  // Reset view
  const resetView = useCallback(() => {
    setZoomLevel(1);
    setPanOffset({ x: 0, y: 0 });
  }, []);
  
  return (
    <div className="h-screen w-full bg-stone-950 text-stone-300 flex flex-col overflow-hidden">

      
      {/* Header */}
      <header className="h-14 bg-stone-900 border-b border-stone-800 flex items-center justify-between px-6 flex-shrink-0">
        <div className="flex items-center gap-4">
          <h1 className="font-serif text-lg text-stone-100 tracking-wide">
            Konstruktionsdetail-Explorer
          </h1>
          <span className="text-stone-600 text-sm">|</span>
          <span className="text-stone-500 text-sm font-light">
            Trockenbauwand → Doppelboden
          </span>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              setSoundEnabled(!soundEnabled);
              if (!soundEnabled) playClickSound();
            }}
            className={`px-3 py-1.5 text-xs border rounded transition-all flex items-center gap-2 ${
              soundEnabled 
                ? 'text-stone-300 border-stone-600 hover:border-stone-500' 
                : 'text-stone-500 border-stone-700 hover:border-stone-600'
            }`}
            title={soundEnabled ? 'Ton ausschalten' : 'Ton einschalten'}
          >
            {soundEnabled ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
                <path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>
                <path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>
              </svg>
            ) : (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
                <line x1="23" y1="9" x2="17" y2="15"/>
                <line x1="17" y1="9" x2="23" y2="15"/>
              </svg>
            )}
            <span className="hidden sm:inline">{soundEnabled ? 'Ton an' : 'Ton aus'}</span>
          </button>
          <div className="text-xs text-stone-600">
            Zoom: {Math.round(zoomLevel * 100)}%
          </div>
          <button 
            onClick={() => {
              resetView();
              if (soundEnabled) playClickSound();
            }}
            className="px-3 py-1.5 text-xs text-stone-400 hover:text-stone-200 border border-stone-700 rounded hover:border-stone-600 transition-all"
          >
            Ansicht zurücksetzen
          </button>
        </div>
      </header>
      
      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Panel - Layer Filters */}
        <aside className="w-56 bg-stone-900 border-r border-stone-800 flex-shrink-0">
          <LayerPanel 
            activeCategory={activeCategory}
            setActiveCategory={setActiveCategory}
            failureMode={failureMode}
            setFailureMode={setFailureMode}
            onButtonClick={() => soundEnabled && playClickSound()}
          />
        </aside>
        
        {/* Center - SVG Viewer */}
        <main 
          ref={svgContainerRef}
          className="flex-1 bg-stone-900/50 relative overflow-hidden cursor-crosshair"
          onMouseMove={handleMouseMove}
          onWheel={handleWheel}
          onClick={handleSVGClick}
          onMouseDown={handleMouseDown}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          style={{ cursor: isPanning ? 'grabbing' : 'crosshair' }}
        >
          {/* Background pattern - subtle dots */}
          <div 
            className="absolute inset-0 opacity-20"
            style={{
              backgroundImage: 'radial-gradient(circle, #555 1px, transparent 1px)',
              backgroundSize: '24px 24px'
            }}
          />
          
          {/* SVG Container */}
          <div className="absolute inset-4 flex items-center justify-center">
            <div className="w-full h-full max-w-3xl max-h-full bg-[#FAF8F5] rounded shadow-2xl border border-stone-700 overflow-hidden">
              <TechnicalSVG 
                activeComponent={activeComponent}
                setActiveComponent={setActiveComponent}
                activeCategory={activeCategory}
                failureMode={failureMode}
                zoomLevel={zoomLevel}
                panOffset={panOffset}
                onHover={handleComponentHover}
                onClick={handleComponentClick}
              />
            </div>
          </div>
          
          {/* Tooltip */}
          <Tooltip 
            component={activeComponent} 
            position={tooltipPosition}
          />
          
          {/* Zoom Controls */}
          <div className="absolute bottom-4 left-4 flex flex-col gap-1 bg-stone-900/90 rounded border border-stone-700 p-1">
            <button 
              onClick={() => setZoomLevel(prev => Math.min(prev + 0.25, 3))}
              className="w-8 h-8 flex items-center justify-center text-stone-400 hover:text-stone-200 hover:bg-stone-800 rounded transition-colors"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="12" y1="5" x2="12" y2="19"/>
                <line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
            </button>
            <button 
              onClick={() => setZoomLevel(prev => Math.max(prev - 0.25, 0.5))}
              className="w-8 h-8 flex items-center justify-center text-stone-400 hover:text-stone-200 hover:bg-stone-800 rounded transition-colors"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
            </button>
            <div className="border-t border-stone-700 my-1"/>
            <button 
              onClick={resetView}
              className="w-8 h-8 flex items-center justify-center text-stone-400 hover:text-stone-200 hover:bg-stone-800 rounded transition-colors"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="3" width="18" height="18" rx="2"/>
                <path d="M9 3v18"/>
                <path d="M15 3v18"/>
                <path d="M3 9h18"/>
                <path d="M3 15h18"/>
              </svg>
            </button>
          </div>
          
          {/* Active Failure Mode Indicator */}
          {failureMode && (
            <div className="absolute top-4 left-4 bg-red-900/80 border border-red-700 rounded px-3 py-2">
              <div className="text-xs text-red-200 font-semibold">
                Fehlerinspektor aktiv
              </div>
              <div className="text-[10px] text-red-300/80 mt-0.5">
                {FAILURE_SCENARIOS.find(f => f.id === failureMode)?.name}
              </div>
            </div>
          )}
        </main>
        
        {/* Right Panel - Info */}
        <aside className="w-80 bg-stone-900 border-l border-stone-800 flex-shrink-0">
          <InfoPanel 
            componentId={selectedComponent}
            onClose={() => setSelectedComponent(null)}
          />
        </aside>
      </div>
      
      {/* Footer */}
      <footer className="h-8 bg-stone-950 border-t border-stone-800 flex items-center justify-between px-6 text-[10px] text-stone-600 flex-shrink-0">
        <div>Baudetail: Trockenbauwand W112 auf Doppelboden • Maßstab 1:5</div>
        <div>DIN 18181 • DIN 4103 • DIN EN 12825 • DIN 4109</div>
      </footer>
      
      {/* Custom scrollbar styles */}
      <style>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 6px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: transparent;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: #525252;
          border-radius: 3px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: #6b6b6b;
        }
        
        @import url('https://fonts.googleapis.com/css2?family=Crimson+Pro:wght@400;500;600&family=Source+Sans+3:wght@300;400;500&display=swap');
        
        .font-serif {
          font-family: 'Crimson Pro', Georgia, serif;
        }
        
        body {
          font-family: 'Source Sans 3', system-ui, sans-serif;
        }
      `}</style>
    </div>
  );
}
