# Reporting — Anonyme EEG-Community-Statistik

Zukunftskonzept für zentrales Reporting aller EEG-Installationen.

## Ziel

Zentrale Erfassung wann welche Installation (anonym per UUID) Ladung blockiert oder abends entladen hat — wie lange und wie viel Energie. Gruppierung per Nahbereich-ID (= Trafo-Zuordnung).

## Datenmodell

### Events

| Feld | Beispiel | Zweck |
|------|----------|-------|
| `installation_id` | UUID (einmalig, persistent) | Wiedererkennung ohne Personenbezug |
| `event_type` | `morning_block` / `evening_discharge` | Was passiert ist |
| `started_at` | ISO-Timestamp | Beginn |
| `ended_at` | ISO-Timestamp | Ende |
| `duration_minutes` | 142 | Dauer |
| `energy_kwh` | 3.7 | Energiemenge |
| `peak_power_kw` | 2.1 | Max. Leistung |

### Installation (Registrierung)

| Feld | Beispiel |
|------|----------|
| `installation_id` | UUID |
| `eeg_name` | "EEG Musterstadt" |
| `nahbereich_id` | "3.042.017" |
| `api_key` | generierter Key |
| `registered_at` | ISO-Timestamp |

## Nahbereich-ID

- Offizielle Trafo-Zuordnung der österreichischen Netzbetreiber
- Nicht automatisch ableitbar — User trägt sie manuell ein (von Stromrechnung oder Quick-Check beim Netzbetreiber)
- Format z.B. `3.042.017` (Netzebene.Umspannwerk.Trafostation)
- Gleiche komplette ID = selber Trafo = lokale EEG

## Architektur: Cloudflare (alles kostenlos)

```
Cloudflare (Free Tier):

  Pages + Access (Dashboard)
  ├── HTML/JS Dashboard-App, teilbar per Link
  ├── Auth via Cloudflare Access (E-Mail-Code, bis 50 User kostenlos)
  └── Nur freigegebene E-Mail-Adressen haben Zugang

  Workers (API)
  ├── POST /api/events     ← HA-Integration sendet Events (API-Key Auth)
  ├── GET  /api/stats      ← Dashboard liest Statistiken (Access Auth)
  ├── POST /api/register   ← Neue Installation registrieren
  └── 100.000 Requests/Tag kostenlos

  D1 (Datenbank)
  ├── SQLite, 5 GB kostenlos
  └── Tabellen: events, installations, api_keys
```

### Warum Cloudflare?

- Keine Infrastrukturkosten, keine Kreditkarte nötig
- Auth (Cloudflare Access) bis 50 User kostenlos inklusive
- Dashboard teilbar per Link mit E-Mail-basiertem Login
- API + DB + Hosting unter einem Dach

### Verworfene Alternativen

| Option | Grund |
|--------|-------|
| Supabase | Auto-REST-API, aber Dashboard nicht teilbar ohne eigenes Frontend |
| Google Sheets | Zu langsam, max ~100 Installationen |
| Firebase | NoSQL, schwierig für Aggregationen |
| GPS statt Nahbereich-ID | Datenschutzproblem, keine API der Netzbetreiber |

## Integration-seitig (HA Custom Component)

1. **UUID-Generierung** beim ersten Setup, persistent im Config Entry
2. **Opt-in Toggle** im Panel ("Community-Statistik aktivieren")
3. **Konfiguration**: EEG-Name, Nahbereich-ID, Backend-URL
4. **Event-Tracker** im Optimizer: erkennt Start/Ende von Blocking/Discharge, misst Dauer + Energie
5. **Reporter-Modul**: sendet Events per `aiohttp` POST (fire-and-forget, Fehler still geschluckt)

## Dashboard-Features (geplant)

- Übersicht aller Installationen pro EEG / Nahbereich-ID
- Zeitreihen: Blocking- und Discharge-Events über Zeit
- Aggregationen: Gesamtenergie pro Trafo, pro Tag/Woche/Monat
- Filter: EEG, Nahbereich-ID, Zeitraum, Event-Typ
