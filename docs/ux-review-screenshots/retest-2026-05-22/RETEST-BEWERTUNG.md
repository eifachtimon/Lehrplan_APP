# UX-Retest nach Quick Wins (22.05.2026)

Desktop **1440×900**, lokale App `http://localhost:3002`.

Screenshots in diesem Ordner (`retest-*.png`), Vergleich mit Ersttest `../01-*.png` … `08-*.png`.

---

## Kurzfazit

| Bereich | Vorher (Ersttest) | Nachher (Retest) | Bewertung |
|--------|-------------------|------------------|-----------|
| **Hub** | 4+ gelbe/weiße Blöcke, Onboarding 3 Spalten, eigene Heute-Karte | Eine Fokus-CTA mit Heute inline, Onboarding 1 Zeile, Neues+Vorhaben nebeneinander | **Deutlich ruhiger** |
| **Suche** | Landkarte-Button im Hero + Sidebar | Nur Sidebar-Hinweis, Fächer eingeklappt | **Klarer** |
| **Landkarte** | Langer Split-Fließtext, viele Schatten | Kein Fließtext, Trenner „Ziehen“, flachere Zeilen | **Besser** |
| **Jahresplan** | 1 Spalte (CSS-Bug) | Mehrspaltiges Raster sichtbar | **Fix bestätigt** |
| **Kalender** | Viele Leisten, Abos oft offen | „Leisten ein“ aktiv, Raster dominiert | **Besser** |
| **Vorhaben** | Kompetenz-Picker immer sichtbar | Block einklappbar (`details`) | **Weniger Scroll-Stress** |

**Gesamt:** Die App wirkt **fokussierter und weniger gestapelt**. Offen bleiben vor allem **Sidebar-Dichte**, **abgeschnittene Inhalte bei schmaler Main-Spalte** (Browser-Screenshots zeigen viel rechts abgeschnitten — Layout nutzt Sidebar + begrenzte Content-Breite) und **Landkarte** (viele Outline-Ebenen).

---

## Screenshots

| Datei | Inhalt |
|-------|--------|
| `retest-01-suche.png` | Suche mit Treffer, Fächer zu |
| `retest-02-planung-hub-viewport.png` | Hub (Viewport, empfohlen) |
| `retest-02-planung-hub.png` | Hub (Full-Page, teils abgeschnitten) |
| `retest-03-landkarte-split.png` | Landkarte Italienisch, Split |
| `retest-03b-landkarte-kette.png` | Landkarte mit gewählter Kette |
| `retest-04-jahresplan.png` | Jahresplan Raster |
| `retest-05-kalender.png` | Kalender Woche, max. Platz |
| `retest-06-vorhaben-grob.png` | Grobplanung (Kompetenzen zu) |

---

## Detail pro Ansicht

### Hub (`retest-02-planung-hub-viewport.png`)

**Positiv**
- Gelber Block „Weiter planen“ ist klar die Hauptaktion.
- „Heute · KW …“ steht in derselben Karte (keine zweite Karte mehr).
- Onboarding: *„Neu hier? 3 Schritte“* + **Anzeigen** — nicht mehr drei Spalten standardmäßig.
- Rechts: Neues Vorhaben | Deine Vorhaben in zwei Spalten.

**Noch verbesserbar**
- Sidebar + Top-Nav + gelber Hub-Header = weiterhin viel Navigation.
- Rechter Rand: Hub-Inhalt wirkt schmal (viel Graufläche rechts im Viewport-Screenshot durch Sidebar).

### Suche (`retest-01-suche.png`)

**Positiv**
- Kein zweiter Landkarte-Einstieg im Titel.
- Untertitel verweist auf Sidebar.
- Fächer-Panel zu → Zyklus + Suche + Ergebnis dominieren.

**Noch verbesserbar**
- „Ergebnisse · 1 Treffer“ sehr hell (Kontrast).
- Filterzeile noch vor dem Ergebnis (akzeptabel, aber bei leerer Suche prüfen).

### Landkarte (`retest-03*`, `retest-03b*`)

**Positiv**
- Kein gelber Hinweis-Balken mehr unter dem Header.
- Explorer-Zeilen ohne harte Schatten.
- Split mit rechter „Aufbau-Kette“ funktioniert; Kette öffnet bei Klick.

**Noch verbesserbar**
- Gelber Header + Breadcrumb + Emoji + Zur Suche = viel Kopf.
- Hinweistext *„Struktur für Italienisch. Andere Fächer…“* noch technisch/lang.
- Rechte Spalte vor Auswahl leer (erwartbar; ggf. schmaler bis zur Auswahl).

### Jahresplan (`retest-04-jahresplan.png`)

**Positiv**
- Monatskarten im **Raster** (Bugfix wirkt).

**Noch verbesserbar**
- Im Viewport nur teilweise sichtbar (Scroll); auf sehr breiten Monitoren mehr Spalten nutzen.
- „Monatsplan →“ pro Karte repetitiv.

### Kalender (`retest-05-kalender.png`)

**Positiv**
- Button **„Leisten ein“** (pressed) → mehr Rasterfläche.
- Abos nicht im sichtbaren Bereich.

**Noch verbesserbar**
- Im engen Viewport: Kalender-Raster rechts abgeschnitten — Sidebar + Content-Breite prüfen.
- FullCalendar-Buttons (blau) vs. Bauhaus-Ghost noch gemischt.

### Vorhaben Grob (`retest-06-vorhaben-grob.png`)

**Positiv**
- Kompetenzen als **zugeklappter** Block (nicht mehr sofort der ganze Picker).

**Noch verbesserbar**
- Formularlänge (Phasen, FHNW) bleibt die schwerste Seite.
- Stepper + viele Felder = weiterhin hohe kognitive Last.

---

## Nachfolge-Fixes (gleicher Tag)

- **Breite:** `bauhaus-layout-width.css` — Main-Inhalt 100 % neben Sidebar.
- **Landkarte:** Fließtext-Hinweis entfernt, Tooltip am Explorer.
- **Suche:** Kontrast `Ergebnisse · X Treffer` (dunkleres Grau).
- **Kalender:** FullCalendar-Buttons wie Ghost-Buttons (weiß/Gelb aktiv).
- **Sidebar Bibliothek:** kürzerer Hinweis.
- **Jahresplan:** nur Monats-Link im Titel (kein extra „Monatsplan →“).

---

*Erstellt automatisch im Browser-Retest nach Umsetzung der Quick Wins.*
