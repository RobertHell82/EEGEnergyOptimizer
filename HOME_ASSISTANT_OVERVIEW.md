# Home Assistant Installation - Übersicht

**URL:** http://192.168.100.211:8123
**Version:** 2026.3.1
**Standort:** Home (2 Standorte: Grünbach Haupthaus + Traun)
**Gesamt:** 3.417 Entitäten | 226 Komponenten
**Erfasst am:** 2026-03-13

---

## Personen

| Person | Entity | Status |
|--------|--------|--------|
| Robert Hell | person.roberthell | home |
| Melanie Hell | person.melanie_hell | home |
| Michael Döberl | person.michael_doberl | home |
| Anna Döberl | person.anna_doberl | home |

---

## Standort: Grünbach (Haupthaus OG + UG)

### Räume (abgeleitet aus Entitäten)

**OG (Obergeschoß):**
- Wohnen, Kochen, Essen, Schlafen, Bad, WC, Diele, Gang, Schleuse, Speis, Stiegenhaus, Terasse

**UG (Untergeschoß):**
- Kinder, Schlafen, Bad, WC, Büro, Gang, Technikraum, Geräteraum, Vorratskeller, Terasse

**Außen:**
- Garage, Hauseingang, Garten, Gartenhütte, Erdäpfelkeller

---

### Energie / Solar

| Entity | Beschreibung | Aktuell |
|--------|-------------|---------|
| sensor.hell_doberl_grunbach_leistung_ac | Fronius Wechselrichter AC Leistung | 460 W |
| sensor.solarnet_pv_leistung | PV-Leistung | 1.5 W |
| sensor.solarnet_leistung_verbrauch | Hausverbrauch | 428 W |
| sensor.solarnet_leistung_netzeinspeisung | Netzeinspeisung | 49 W |
| sensor.solarnet_leistung_netzbezug | Netzbezug | 0 W |
| sensor.solarnet_entladeleistung | Batterie Entladung | 516 W |
| sensor.solarnet_ladeleistung | Batterie Ladung | 0 W |
| sensor.byd_battery_box_premium_hv_ladezustand | BYD Batterie SOC | 82.2% |
| sensor.ohmpilot_leistung | Ohmpilot (Warmwasser) | 0 W |
| sensor.smart_meter_ts_65a_3_wirkleistung | Smart Meter | -49.2 W |

**Energie-Zähler:**
- sensor.photovoltaics_energy - PV Gesamt: 15.406 kWh
- sensor.battery_energy_charged - Batterie geladen: 3.186 kWh
- sensor.battery_energy_discharged - Batterie entladen: 2.985 kWh
- sensor.smart_meter_ts_65a_3_bezogene_wirkenergie - Netzbezug: 1.057 kWh
- sensor.smart_meter_ts_65a_3_eingespeiste_wirkenergie - Einspeisung: 5.546 kWh
- sensor.ohmpilot_verbrauchte_energie - Ohmpilot: 5.180 kWh
- sensor.eigenverbrauch - Eigenverbrauch: 5.538 kWh

**Solcast Prognose:**
- sensor.solcast_pv_forecast_prognose_heute - Prognose heute: 60.5 kWh
- sensor.solcast_pv_forecast_prognose_nachste_stunde
- sensor.solcast_pv_forecast_prognose_aktuelle_stunde
- sensor.solcast_pv_forecast_prognose_verbleibende_leistung_heute

**Steuerung:**
- input_boolean.batterie_verwenden - Batterie entladen
- input_boolean.einspeiseoptimierung - Einspeiseoptimierung
- input_boolean.fixe_einspeisung - Fixe Einspeisung

---

### Heizung

**Thermostate Shelly (Grünbach):**

| Entity | Raum | Modus |
|--------|------|-------|
| climate.thermostat_og_wohnen | OG Wohnen | auto |
| climate.thermostat_og_essen | OG Essen | auto |
| climate.thermostat_og_schlafen | OG Schlafen | auto |
| climate.thermostat_og_bad | OG Bad | auto |
| climate.thermostat_og_schleuse | OG Schleuse | auto |
| climate.thermostat_ug_kinder | UG Kinder | auto |
| climate.thermostat_ug_schlafen | UG Schlafen | auto |
| climate.thermostat_ug_bad | UG Bad | auto |
| climate.thermostat_ug_buro | UG Büro | auto |

**Heizkreise & Steuerung:**
- switch.heizkreis_og - Heizkreis OG (off)
- switch.heizkreis_ug - Heizkreis UG (on)
- switch.fernwarme - Fernwärme (off)
- input_boolean.heizungsautomatik - Heizungsautomatik (on)
- switch.schaltaktor_a7_ch14 - Wohnraumlüftung (on)
- switch.badheizkoerper_heizen - Badheizkörper (off)

**Pufferspeicher:**
- sensor.puffer_oben_temperatur - Puffer oben: 58.3°C
- sensor.ohmpilot_temperatur - Puffer mitte: 37.7°C
- sensor.puffer_unten_temperatur - Puffer unten: 21.9°C

**Holzvergaser:**
- switch.holzvergaser_pumpe - Umwälzpumpe (off)
- sensor.holzvergaser_temperature - Temperatur: 23.5°C
- sensor.holzvergaser_vorlauf_temperature - Vorlauf: 23.2°C
- sensor.holzvergaser_rucklauf_temperature - Rücklauf: 22.9°C

---

### Rollläden & Raffstores (Grünbach - Shelly)

| Entity | Beschreibung | Status |
|--------|-------------|--------|
| cover.rollladen_og_wohnen_links | OG Wohnen links | closed |
| cover.rollladen_og_wohnen_rechts | OG Wohnen rechts | closed |
| cover.rollladen_og_wohnen_terasse | OG Wohnen Terasse | closed |
| cover.rollladen_og_kochen | OG Kochen | closed |
| cover.raffstore_og_essen | Raffstore OG Essen | closed |
| cover.raffstore_og_essen_links | Raffstore OG Essen links | closed |
| cover.raffstore_og_essen_rechts | Raffstore OG Essen rechts | closed |
| cover.rollladen_og_schlafen | OG Schlafen | closed |
| cover.rollladen_og_bad | OG Bad | closed |
| cover.rollladen_og_wc | OG WC | closed |
| cover.rollladen_ug_kinder | UG Kinder | closed |
| cover.rollladen_ug_schlafen_fenster | UG Schlafen Fenster | closed |
| cover.rollladen_ug_schlafen_tur | UG Schlafen Tür | closed |
| cover.rollladen_ug_bad | UG Bad | closed |
| cover.rollladen_ug_wc | UG WC | closed |
| cover.rollladen_ug_buro | UG Büro | closed |
| cover.hmip_mod_ho_00241f298ed591 | Garagentor | closed |

**CCA Automationen** (Rollläden-Automatik pro Raum):
- automation.cca_ug_kinder, cca_ug_schlafen_tur, cca_ug_kinder_fenster, cca_ug_bad, cca_ug_wc, cca_ug_buro
- automation.cca_og_wc, cca_og_bad, cca_og_schlafen, cca_og_wohnen_terassentur, cca_og_wohnen_links, cca_og_wohnen_rechts, cca_og_kochen, cca_og_essen, cca_og_essen_links, cca_og_essen_rechts
- input_boolean.windalarm - Windalarm (off)

---

### Licht (Grünbach - HmIP Wired Schaltaktoren)

**OG:**
- switch.schaltaktor_a6_licht_og_kochen | Kochen | on
- switch.schaltaktor_a6_licht_og_kochen_fenster | Kochen Fenster | off
- switch.schaltaktor_a6_licht_og_kochen_insel | Kochen Insel | on
- switch.schaltaktor_a6_licht_og_essen | Essen | off
- switch.schaltaktor_a6_licht_og_bad | Bad | off
- switch.schaltaktor_a6_licht_og_bad_alibert | Bad Alibert | off
- switch.schaltaktor_a6_licht_og_speis | Speis | off
- switch.schaltaktor_a6_licht_og_gang | Gang | off
- switch.schaltaktor_a5_licht_og_wc | WC | off
- switch.schaltaktor_a5_licht_og_diele | Diele | off
- switch.schaltaktor_a5_licht_og_schleuse | Schleuse | off
- switch.schaltaktor_a7_licht_og_stiegenhaus | Stiegenhaus | off
- switch.schaltaktor_a7_licht_og_terasse | Terasse | off
- switch.schaltaktor_a7_licht_og_terassenture | Terassentüre | off
- light.dimmaktor_a8_licht_og_wohnen | Wohnen (Dimmer) | on
- light.dimmaktor_a8_licht_og_schlafen | Schlafen (Dimmer) | off

**UG:**
- switch.schaltaktor_a4_licht_ug_gang | Gang 1 | off
- switch.schaltaktor_a4_vch27 | Gang 2 | off
- switch.schaltaktor_a4_vch28 | Gang (Schaltaktor) | off
- switch.schaltaktor_a4_licht_ug_nachtlicht | Nachtlicht 1 | off
- switch.schaltaktor_a4_vch31 | Nachtlicht 2 | on
- switch.schaltaktor_a4_vch32 | Nachtlicht (Schaltaktor) | off
- switch.schaltaktor_a4_licht_ug_bad | Bad | off
- switch.schaltaktor_a4_licht_ug_bad_alibert | Bad Alibert | off
- switch.schaltaktor_a4_licht_ug_wc | WC | off
- switch.schaltaktor_a4_licht_ug_kinder | Kinder | off
- switch.schaltaktor_a4_licht_ug_buro | Büro | off
- switch.schaltaktor_a4_licht_ug_technikraum | Technikraum | off
- switch.schaltaktor_a5_licht_ug_gerateraum | Geräteraum | off
- switch.schaltaktor_a5_licht_ug_vorratskeller | WC Spiegel | off
- switch.schaltaktor_a5_licht_ug_terasse | Terasse | off
- switch.schaltaktor_a5_licht_ug_aussen | Außen | off
- switch.schaltaktor_a5_licht_ug_led_stiege | LED Stiege | off
- light.dimmaktor_a8_licht_ug_schlafen | Schlafen (Dimmer) | off

**Außen:**
- light.hmip_rgbw_0033e0c99236f2 | LED Hauseingang | off
- light.hmip_rgbw_0033e0c98dafc7 | LED Garage | off
- input_boolean.led_farbenwechsel | LED Farbenshow | off
- switch.hmipw_drs8_00161f29abc2f7_ch2 | Licht Garage | off
- switch.hmipw_drs8_00161f29abc2f7_ch10 | Garage Waschbecken | off
- switch.hmipw_drs8_00161f29abc2f7_ch14 | Garage Werkstatt | off
- switch.hmipw_drs8_00161f29abc2f7_ch18 | Garage Garten | on

---

### Kameras (Reolink)

| Entity | Beschreibung |
|--------|-------------|
| camera.og_garage_standardauflosung | OG Garage |
| camera.kamera_og_klar | OG Kamera (Hochauflösung) |
| camera.kamera_og_fliessend | OG Kamera (Low Quality) |
| camera.ug_kamera_klar | UG Kamera (Low Quality) |
| camera.ug_kamera_flussig | UG Kamera Standardauflösung |
| camera.ug_kamera_schnappschusse_klar | UG Kamera Schnappschüsse HD |
| camera.ug_kamera_schnappschusse_flussig | UG Kamera Schnappschüsse SD |

**Bewegungsmelder:**
- binary_sensor.og_garage_bewegung
- binary_sensor.kamera_og_bewegung
- binary_sensor.ug_kamera_bewegung
- binary_sensor.bewegungsmelder_og_schleuse_bewegung
- binary_sensor.bewegungsmelder_og_speis_bewegung
- binary_sensor.hmip_smo_2_0031e0c998e6f9_bewegung | UG Geräteraum

---

### Türschlösser

| Entity | Beschreibung | Status |
|--------|-------------|--------|
| lock.hmip_dld_002a1d89b42b50 | Haustüre OG | unlocked |
| lock.hmip_dld_002a20c996ade9 | Haustüre UG | unlocked |

---

### Fensterkontakte

| Entity | Beschreibung | Status |
|--------|-------------|--------|
| binary_sensor.eingangsmodul_a3_fenster_tur_og_wohnen | OG Wohnen Tür | off |
| binary_sensor.eingangsmodul_a3_fenster_schiebetur_og_wohnen | OG Wohnen Schiebetür | off |
| binary_sensor.eingangsmodul_a3_fenster_tur_og_kochen | OG Kochen Tür | off |
| binary_sensor.eingangsmodul_a3_fenster_fenster_og_essen | OG Essen Fenster | off |
| binary_sensor.eingangsmodul_a3_fenster_tur_og_schlafen | OG Schlafen Tür | off |
| binary_sensor.eingangsmodul_a3_fenster_fenster_og_bad | OG Bad Fenster | off |
| binary_sensor.eingangsmodul_a3_fenster_fenster_og_wc | OG WC Fenster | off |
| binary_sensor.eingangsmodul_a3_fenster_ture_ug_kinder | UG Kinder Tür | off |
| binary_sensor.eingangsmodul_a3_fenster_fenster_ug_schlafen | UG Schlafen Fenster | off |
| binary_sensor.eingangsmodul_a3_fenster_ture_ug_schlafen | UG Schlafen Tür | off |
| binary_sensor.eingangsmodul_a3_fenster_fenster_ug_bad | UG Bad Fenster | off |
| binary_sensor.eingangsmodul_a3_fenster_fenster_ug_wc | UG WC Fenster | off |
| binary_sensor.eingangsmodul_a3_fenster_fenster_ug_buro | UG Büro Fenster | off |

---

### Rauchmelder

- binary_sensor.rauchmelder_og_gang_rauchalarm | OG Gang
- binary_sensor.rauchmelder_ug_gang_rauchalarm | UG Gang
- binary_sensor.rauchmelder_garage_rauchalarm | Garage
- binary_sensor.rauchmelder_ug_technikraum_rauchalarm | UG Technikraum

---

### Temperatursensoren (Grünbach)

**Raumtemperaturen (via Thermostate):**
- sensor.thermostat_og_wohnen_temperatur, _luftfeuchtigkeit
- sensor.thermostat_og_essen_temperatur, _luftfeuchtigkeit
- sensor.thermostat_og_schlafen_temperatur, _luftfeuchtigkeit
- sensor.thermostat_og_bad_temperatur, _luftfeuchtigkeit
- sensor.thermostat_og_schleuse_temperatur, _luftfeuchtigkeit
- sensor.thermostat_ug_kinder_temperatur, _luftfeuchtigkeit
- sensor.thermostat_ug_schlafen_temperatur, _luftfeuchtigkeit
- sensor.thermostat_ug_bad_temperatur, _luftfeuchtigkeit
- sensor.thermostat_ug_buro_temperatur, _luftfeuchtigkeit

**Sonstige:**
- sensor.temperatur_gartenhutte_temperatur | Gartenhütte: 9.4°C
- sensor.shellyhtg3_e4b3232f6eb4_temperatur | Erdäpfelkeller: 13.4°C
- sensor.byd_battery_box_premium_hv_temperatur | BYD Batterie: 14.0°C

---

### Media Player

| Entity | Beschreibung | Status |
|--------|-------------|--------|
| media_player.wohnzimmer | TV (Android TV) | on |
| media_player.wohnzimmer_2 | TV (Cast) | playing |
| media_player.wohnzimmer_3 | Wohnzimmer (DLNA) | idle |

---

### Tesla

| Entity | Beschreibung |
|--------|-------------|
| sensor.tesla_batteriestand | Batteriestand |
| climate.tesla_klima | Klimaanlage |
| lock.tesla_schloss | Türschloss |
| cover.tesla_ladeanschluss_klappe | Ladeklappe |
| cover.tesla_front_kofferraum | Frunk |
| cover.tesla_kofferraum | Kofferraum |
| switch.tesla_aufladung | Laden |
| switch.tesla_wachter_modus | Wächter-Modus |
| switch.tesla_entfrosten | Entfrosten |

---

### Wallbox (go-eCharger 073871) - derzeit offline

- sensor.goe_073871_nrg_11 | Totale Leistung
- sensor.goe_073871_car_value | Fahrzeug Status
- sensor.goe_073871_modelstatus_value | Status
- switch.goe_073871_fup | PV-Überschuss laden
- switch.goe_073871_fzf | Zero Feed-in

---

### Netzwerk (FritzBox 7590 AX)

- switch.fritz_box_7590_ax_wi_fi_hdlan_2_4ghz | WLAN 2.4GHz (on)
- switch.fritz_box_7590_ax_wi_fi_hdlan_5ghz | WLAN 5GHz (on)
- switch.fritz_box_7590_ax_wi_fi_hdfritzbox_gastzugang | Gastzugang (off)

---

## Standort: Traun

### Klima/Heizung

| Entity | Raum | Modus |
|--------|------|-------|
| climate.traun_wandthermostat_kuche_essen | Küche/Essen | heat |
| climate.traun_wandthermostat_schlafen | Schlafen | heat |
| climate.traun_wandthermostat_bad | Bad | heat |
| climate.traun_wandthermostat_nina | Nina | heat |
| climate.traun_wandthermostat_florian | Florian | heat |
| climate.traun_wandthermostat_keller | Keller | heat |
| climate.traun_wandthermostat_buro | Büro | heat |

### Temperaturen & Luftfeuchtigkeit

- sensor.traun_wandthermostat_kuche_essen_temperatur / _luftfeuchtigkeit | Essen: 22.2°C / 38%
- sensor.traun_wandthermostat_schlafen_temperatur / _luftfeuchtigkeit | Schlafen: 38%
- sensor.traun_wandthermostat_bad_temperatur / _luftfeuchtigkeit | Bad: 38%
- sensor.traun_wandthermostat_nina_temperatur / _luftfeuchtigkeit | Nina: 41%
- sensor.traun_wandthermostat_florian_temperatur / _luftfeuchtigkeit | Florian: 39%
- sensor.traun_wandthermostat_keller_temperatur / _luftfeuchtigkeit | Keller: 59%
- sensor.traun_wandthermostat_buro_temperatur / _luftfeuchtigkeit | Büro: 39%
- sensor.traun_temperatur_terasse_temperatur | Außentemperatur (unavailable)

### Rollläden

| Entity | Beschreibung | Status |
|--------|-------------|--------|
| cover.traun_rollladen_schlafen_pool | Schlafen Pool | open |
| cover.traun_rollladen_schlafen_garten | Schlafen Garten | open |
| cover.traun_rollladen_florian_strasse | Florian Straße | open |
| cover.traun_rollladen_florian_pool | Florian Pool | open |
| cover.traun_rollladen_nina | Nina | open |
| cover.traun_markise_terasse | Markise Terasse | closed |
| cover.traun_vertikaljalousie_terasse | Vertikaljalousie Terasse | closed |
| cover.traun_garagentortaster | Garagentor | closed |

### Licht

- switch.traun_licht_buro | Büro (off)
- switch.traun_licht_bad | Bad (off)
- switch.traun_licht_kellerstiege | Kellerstiege (off)
- switch.traun_licht_stiegenhaus | Stiegenhaus (off)
- switch.traun_licht_garderobe | Garderobe (off)
- switch.traun_aussenlicht_brille | Außenlicht Brille (off)

### Haustüre & Katzenklappe

- lock.traun_hausture | Haustüre (locked)
- lock.traun_klappe_locked_in | Katzenklappe innen (unlocked)
- lock.traun_klappe_locked_out | Katzenklappe außen (locked)
- lock.traun_klappe_locked_all | Katzenklappe komplett (unlocked)
- sensor.traun_klappe_battery_level | Katzenklappe Batterie: 10%

### Pool & Solar

- switch.traun_poolpumpe_solar | Poolpumpe Solar (unavailable)
- switch.traun_ventilator_poolschacht | Ventilator Poolschacht (unavailable)
- sensor.traun_temperatur_pool_solar_temperaturdifferenz_solar_pool_temperatur

### Media

- media_player.traun_wohnzimmer | Wohnzimmer (off)

### Bewegungsmelder

- binary_sensor.traun_bewegungsmelder_garderobe_1_bewegung
- binary_sensor.traun_bewegungsmelder_garderobe_2_bewegung
- binary_sensor.traun_bewegungsmelder_kellerstiege_1_bewegung
- binary_sensor.traun_bewegungsmelder_kellerstiege_2_bewegung

### Rauchmelder

- binary_sensor.traun_rauchmelder_kuche_rauchalarm

### Wechselrichter (Traun)

- switch.traun_inverter_inverter_ein_aus | Inverter (on)
- switch.traun_batteries_laden_aus_dem_netz | Laden aus Netz (off)
- sensor.traun_inverter_interne_temperatur | 37.3°C

---

## Wetter

- weather.forecast_grunbach | Grünbach: 5.5°C
- weather.forecast_traun | Traun: 6°C

---

## Automationen (Übersicht)

| Automation | Beschreibung |
|-----------|-------------|
| CCA * (17x) | Rollläden-Automatik pro Fenster (Beschattungsautomatik) |
| Heizkreis OG/UG | Heizkreissteuerung |
| Fußbodenheizung OG/UG | Fußbodenheizung-Steuerung |
| Wohnraumlüftung | Lüftungssteuerung |
| Heizstab | Heizstab-Steuerung |
| Umwälzpumpe Holzvergaser | Holzvergaser-Pumpensteuerung |
| Batterie aktivieren/deaktivieren | Ohmpilot/Batterie Sollwert |
| Rauchalarmierung | Rauchmelder-Alarm |
| Windalarm | Windschutz Rollläden |
| Bewegung OG/UG | Außenlicht bei Bewegung |
| Klingel | Türklingel |
| Badheizkörper Taste oben/unten | Badheizkörper Steuerung |
| LED Farbenshow | LED Farbwechsel |
| Garagentortaster Traun | Garagentor Traun |
| Katzenklappe verriegeln/aufsperren | Katzenklappe Traun |

---

## Input Helpers

| Entity | Beschreibung | Status |
|--------|-------------|--------|
| input_boolean.windalarm | Windalarm | off |
| input_boolean.default_dashboard | Default Dashboard | on |
| input_boolean.heizungsautomatik | Heizungsautomatik | on |
| input_boolean.batterie_verwenden | Batterie entladen | on |
| input_boolean.led_farbenwechsel | LED Farbenshow | off |
| input_boolean.einspeiseoptimierung | Einspeiseoptimierung | on |
| input_boolean.fixe_einspeisung | Fixe Einspeisung | off |

---

## Key Integrations

- **Homematic IP (Local)** - Fußbodenheizung, Rollläden (Traun), Licht, Türschlösser, Fensterkontakte, Bewegungsmelder, Rauchmelder, Wired Schaltaktoren
- **Shelly** - Thermostate, Rollläden/Raffstores (Grünbach), Temperatursensoren
- **Fronius / SolarNet** - PV-Anlage, Batterie, Smart Meter, Ohmpilot
- **Solcast Solar** - PV-Prognose
- **Reolink** - 3 Kameras
- **Tesla Fleet** - Tesla Fahrzeug
- **go-eCharger** - Wallbox (derzeit offline)
- **Android TV Remote** - TV Steuerung
- **Google Cast** - Chromecast
- **DLNA** - Media Renderer
- **FritzBox** - Netzwerk, Internetsteuerung
- **HACS** - Custom Components installiert
- **Met.no** - Wettervorhersage
