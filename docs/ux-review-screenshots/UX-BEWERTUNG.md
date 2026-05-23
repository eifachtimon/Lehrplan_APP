# UX-Bewertung (Screenshots, Desktop 1440×900)

Erstellt am 22.05.2026 — lokale App unter `http://localhost:3002`.

## Screenshots

| Datei | Ansicht |
|-------|---------|
| `01-suche-mit-ergebnissen.png` | Suche mit Filter + 1 Treffer |
| `02-planung-hub.png` | Mein Unterricht (Hub) |
| `03-landkarte-faecher.png` | Landkarte — Fachauswahl |
| `04-landkarte-split-explorer.png` | Landkarte — Split (Explorer + leere Kette) |
| `05-landkarte-split-kette.png` | Landkarte — Split mit Aufbau-Kette |
| `06-jahresplan.png` | Jahresplan (Schuljahr) |
| `07-kalender-woche.png` | Kalender Wochenansicht |
| `08-vorhaben-grobplanung.png` | Vorhaben — Grobplanung |

---

## Gesamteindruck

Die Bauhaus-Richtung (Rahmen, Gelb, klare Typo) ist erkennbar und wirkt **seriös und lehrkräftig-tauglich**. Gleichzeitig wirkt die Oberfläche für neue Nutzerinnen oft **überladen**: viele gleichwertige Karten, doppelte Navigation (Sidebar + Location-Bar + Top-Nav) und viel Hilfstext auf einmal.

**Stärken:** klare aktive Zustände (Gelb), gute Lesbarkeit der Haupttexte, Kalender nutzt die Breite gut.

**Schwächen:** zu viele „gleich laute“ Boxen, Landkarte-Split erklärt sich nicht von selbst, Hub stapelt zu viele Einstiege, Suche filtert visuell schwerer als der Treffer.

---

## 1. Suche (`01`)

**Wirkt gut:** Suchfeld und Ergebnis-Karte sind klar; Fach-Badge und grüner Akzent geben Orientierung.

**Verwirrend / überladen:**
- **Zwei Navigations-Ebenen:** Sidebar (Suche, Landkarte, …) + Top-Nav + ggf. Location-Bar — Nutzer fragt: „Wo bin ich, was ist die App?“
- **Filterblock:** Alle Fächer als lange Chip-Reihe ohne klappbare Gruppe — auf Desktop viel Fläche, kognitiv „noch vor der Suche“
- **Landkarte-Explorer** als blauer Link neben dem Titel konkurriert mit Sidebar-Eintrag „Landkarte“
- **Bibliothek-Hinweis** in der Sidebar ist lang; Merkliste leer — viel Text für wenig Nutzen beim ersten Besuch

**Empfehlung:** Hero kompakter nach erster Suche; Fächer in aufklappbares Panel; ein klarer Primärweg „Suchen → Merken → Ins Vorhaben“.

---

## 2. Mein Unterricht / Hub (`02`)

**Wirkt gut:** Gelber Hub-Header und „Weiter planen“-CTA sind die richtige Hierarchie.

**Verwirrend / überladen:**
- **Vier gelbe/weiße Blöcke untereinander** (Onboarding, Weiter planen, Heute, Neues Vorhaben, Vorhabenliste) — alles wirkt „wichtig“
- **Onboarding** (3 Schritte) konkurriert mit Sidebar-Zeit-Links (Jahr/Monat/Kalender)
- **„Heute“** und **„Weiter planen“** überschneiden sich inhaltlich (beides → Woche/Kalender)
- Sekundäre Hub-Karten (Jahresplan/Monatsplan) fehlen im Screenshot weit unten — viel Scrollen

**Empfehlung:** Hub auf **max. 3 Zonen** reduzieren: (1) Weiter planen, (2) Heute, (3) Neues Vorhaben + kompakte Vorhabenliste. Onboarding ausblendbar/einklappbar nach erstem Besuch.

---

## 3. Landkarte (`03`–`05`)

**Wirkt gut:** Workspace im Hauptbereich (nicht mehr dunkles Vollbild-Overlay); gelber Kopf; Fachkacheln mit Emoji sind einladend; Split mit Kette funktioniert technisch.

**Verwirrend / überladen:**
- **Gelber Header + Breadcrumb + Split-Hinweis + Emoji-Toggle + Zur Suche** — viel Kopfzeile vor dem Inhalt
- **Split-Hinweis** („Gelber Balken ziehen…“) ist für Lehrkräfte ungewohnt — Feature Discovery fehlt
- **Explorer links** mit verschachtelten Rahmen (Kasten im Kasten) — visuell laut, Hierarchie schwer scanbar
- **Rechte Spalte** vor Klick nur Platzhalter — ok, aber 50 % Breite für „Wähle links…“ wirkt leer/frustrierend
- **Fach-Chips oben** scrollen horizontal — auf Desktop oft abgeschnitten (nur 6 Fächer sichtbar)
- Dunkle Fachkarten in `03` vs. helle Explorer-Liste in `04` — **zwei visuelle Welten** in einer Ansicht

**Empfehlung:** Standard-Split 65/35; Hinweis nur einmal (Tooltip am Trenner); Explorer-Outline flacher (weniger verschachtelte Borders); leere Kette als schmale Spalte oder Sheet statt halber Bildschirm.

---

## 4. Jahresplan (`06`)

**Wirkt gut:** Monatskarten-Raster lesbar; Schuljahr-Navigation klar.

**Verwirrend / überladen:**
- **Nur eine Spalte Monatskarten** trotz breitem Monitor — viel ungenutzte Fläche rechts (Breiten-Thema)
- Jede Karte: Monat + Input + Link „Monatsplan →“ — **repetitiv**, Scroll sehr lang
- Location-Bar / Header fehlen im Screenshot oben teils — Orientierung „Jahresplan“ vs. Sidebar „Jahr“ ist ok, aber redundant

**Empfehlung:** 2–3-spaltiges Raster auf Desktop; Monatskarte kompakter (Monat als Tab, Fokus inline).

---

## 5. Kalender (`07`)

**Wirkt gut:** Wochenraster nutzt Breite; FullCalendar-Toolbar verständlich; Filterzeile strukturiert.

**Verwirrend / überladen:**
- **Viele Toolbar-Zeilen:** Kalender-Header → Filter (Suchen, Filter, +Termin) → FC-Toolbar → ggf. Abo-Panel — **4 Ebenen** vor dem Raster
- **„Leisten ein“ / „Abos“** — unklar ohne Label (im Test war Abo-Panel offen)
- Blaue FC-Buttons vs. Bauhaus-Ghost-Buttons — **zwei Button-Stile**
- „Aktives Vorhaben“-Text im Header nur im Lead — leicht zu übersehen

**Empfehlung:** Filter + FC-Toolbar zusammenführen; Abos in klaren Drawer mit Overlay; einheitliche Button-Komponente.

---

## 6. Vorhaben Grobplanung (`08`)

**Wirkt gut:** Stepper (4 Ebenen) gibt den roten Faden; Phasenmodell-FHNW für Zielgruppe sinnvoll.

**Verwirrend / überladen:**
- **Stepper + Report-Organizer + Phasenmodell + viele Textareas + Kompetenz-Picker** — höchste kognitive Last in der App
- Stepper sticky mit dunklem Alt-Stil (falls noch sichtbar) bricht Bauhaus
- **„4“ Badge** am Stepper ohne Legende
- Kompetenz-Bereich unten: Tabs Merkliste/Suche + leerer Zustand — weiterer großer Block nach langem Formular

**Empfehlung:** Pro Ebene nur **ein** Akkordeon offen; Kompetenzen in Seitenleiste oder Modal; Fortschritt „2/4 Schritte“ im Header.

---

## Navigation — übergreifend

| Problem | Nutzergefühl |
|--------|----------------|
| Sidebar + Top-Nav + Location-Bar | „Drei Menüs“ |
| Landkarte in Sidebar **und** Suche | „Zwei Wege, welcher?“ |
| Zeit: Jahr/Monat/Kalender in Sidebar **und** Planungs-Location-Bar | ok für Profis, redundant für Einsteiger |
| Viele gleich starke Karten | Erschöpfung statt Fokus |

**Empfehlung:** Sidebar = **Bibliothek + Vorhaben + Zeit**; Top-Nav nur Suche | Mein Unterricht; Location-Bar nur innerhalb Planung (nicht auf Suche).

---

## Prioritäten (UX-Roadmap)

1. **Hub entlasten** — weniger gleichzeitige Karten, klare eine Hauptaktion  
2. **Landkarte** — flacherer Explorer, Split erklären/standardisieren, Fachkarten hell  
3. **Suche** — Filter kompakter, Landkarte nur ein Einstieg  
4. **Kalender** — Toolbar-Ebenen reduzieren  
5. **Vorhaben** — Stepper + Formular entflechten, Kompetenzen auslagern  
6. **Breite** — Jahresplan/Hub nutzen mehr Spalten (teilweise schon angegangen)

---

## Umgesetzte Quick Wins (22.05.2026)

- **Hub:** Fokus-Zone „Weiter planen“ mit Heute inline; Onboarding standardmäßig eingeklappt; Neues Vorhaben + Liste nebeneinander (Desktop).
- **Suche:** Doppelter Landkarte-Button im Hero entfernt (nur Sidebar).
- **Landkarte:** Split-Hinweis-Fließtext entfernt, Label am Trenner; Standard-Split 65 %; flachere Explorer-Rahmen.
- **Jahresplan:** Grid-Bug in `bauhaus-spacing.css` behoben (war Flex → eine Spalte).
- **Kalender:** Standard „Mehr Platz“ (Filter-Leiste zu).
- **Vorhaben Grob:** Kompetenzen in ausklappbarem Block.

## Nächster Schritt

Screenshots im Repo: `docs/ux-review-screenshots/`. Bei Bedarf Mobile (375px) und Zustand „leere Merkliste / kein Vorhaben“ separat erfassen.
