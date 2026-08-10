# APS Usage — Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A custom Home Assistant integration for **Arizona Public Service (APS)** customers that provides energy usage, solar generation, and billing sensors — no APS mobile app or CSV download required.

> This project began as a fork of [Conexo-Casa/aps-csv-ha](https://github.com/Conexo-Casa/aps-csv-ha) and now develops independently, adding robust service-agreement detection and solar import/export support.

---

## Sensors

### All accounts

| Sensor | Entity ID | Unit | Description |
|--------|-----------|------|-------------|
| Yesterday kWh | `sensor.aps_yesterday_kwh` | kWh | Prior day's total electricity usage |
| Yesterday On-Peak kWh | `sensor.aps_yesterday_on_peak_kwh` | kWh | Prior day's on-peak (4–7 PM weekdays) usage |
| Yesterday Off-Peak kWh | `sensor.aps_yesterday_off_peak_kwh` | kWh | Prior day's off-peak usage |
| Current Billing Cycle kWh | `sensor.aps_current_billing_cycle_kwh` | kWh | Total kWh since current billing cycle started |
| 30-Day kWh | `sensor.aps_30_day_kwh` | kWh | Rolling 30-day energy total |
| Current Balance | `sensor.aps_current_balance` | USD | Outstanding bill amount |
| Bill Due Date | `sensor.aps_bill_due_date` | date | Next payment due date |
| Last Payment | `sensor.aps_last_payment` | USD | Most recent payment amount |

### Solar accounts (created automatically when APS flags your service agreement as solar)

| Sensor | Entity ID | Unit | Description |
|--------|-----------|------|-------------|
| Yesterday Grid Import kWh | `sensor.aps_yesterday_grid_import_kwh` | kWh | Energy drawn from the grid |
| Yesterday Grid Export kWh | `sensor.aps_yesterday_grid_export_kwh` | kWh | Solar energy sold back to the grid |
| Yesterday Solar Generated kWh | `sensor.aps_yesterday_solar_generated_kwh` | kWh | Total solar production |
| Yesterday Solar Self-Consumed kWh | `sensor.aps_yesterday_solar_self_consumed_kwh` | kWh | Solar energy used on-site |
| Current Cycle Grid Import kWh | `sensor.aps_current_cycle_grid_import_kwh` | kWh | Cumulative grid import this billing cycle |
| Current Cycle Grid Export kWh | `sensor.aps_current_cycle_grid_export_kwh` | kWh | Cumulative grid export this billing cycle |
| Current Cycle Solar Generated kWh | `sensor.aps_current_cycle_solar_generated_kwh` | kWh | Cumulative solar production this billing cycle |

For the Energy Dashboard, use the **statistics** the integration writes directly into HA's recorder (hourly resolution, attributed to the correct day and hour) instead of the cycle sensors — see [Energy Dashboard](#energy-dashboard).

> **Note:** on solar accounts, APS's `totalUsage` (the regular usage sensors) reports **grid import**, not total household consumption. True consumption = Grid Import + Solar Self-Consumed.
>
> Solar support has been verified against a live APS solar account (TOU with demand charge, separate production meter). If your solar sensors are unavailable or wrong, please [open an issue](https://github.com/damianharouff/aps-csv-ha/issues) with your debug logs — account numbers redacted.

All sensors update **every hour**.

### Statistics (Energy Dashboard)

In addition to sensors, the integration writes **hourly long-term statistics** straight into Home Assistant's recorder — these are the recommended [Energy Dashboard](#energy-dashboard) sources:

| Statistic | ID | Created for |
|-----------|----|-------------|
| APS Energy Consumption | `aps_usage:<account>_consumption` | Non-solar accounts |
| APS Grid Import | `aps_usage:<account>_grid_import` | Solar accounts |
| APS Grid Export | `aps_usage:<account>_grid_export` | Solar accounts |
| APS Solar Generation | `aps_usage:<account>_solar_generation` | Solar accounts |

Statistics are not entities — they won't appear in **Developer Tools → States**, only in the Energy Dashboard pickers and **Developer Tools → Statistics**.

---

## Requirements

- Home Assistant **2024.1** or newer
- An active **APS.com account** (aps.com login credentials)
- The `cryptography` Python package (automatically installed by HA)

---

## Installation

### Option A — HACS (Recommended)

1. Open HACS in Home Assistant.
2. Go to **Integrations** → click the **⋮ menu** (top right) → **Custom repositories**.
3. Enter the repository URL:
   ```
   https://github.com/damianharouff/aps-csv-ha
   ```
   Select **Integration** as the category and click **Add**.
4. Search for **APS Usage** in the HACS integrations list and click **Download**.
5. **Restart Home Assistant.**
6. Follow [Configuration](#configuration) below.

### Option B — Manual Installation

1. Clone this repository or download it as a ZIP.
2. Copy the `custom_components/aps_usage/` folder into your Home Assistant config directory:
   ```
   config/
   └── custom_components/
       └── aps_usage/
   ```
3. **Restart Home Assistant.**
4. Follow [Configuration](#configuration) below.

---

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **APS Usage** and click it.
3. Enter your **APS.com username** and **password** (the same credentials you use at [aps.com](https://www.aps.com) or the APS mobile app).
4. Click **Submit**.

The integration authenticates, auto-detects your active service agreement (and production meter, for solar accounts), and creates all sensors. No account ID or meter number is needed — these are discovered automatically.

> **Multiple service addresses / agreements:** If your account has more than one service agreement (multiple addresses, solar production meters, closed accounts), the integration selects the **active consumption agreement** automatically. The `premise_address` attribute on each sensor shows which address is in use.

---

## Energy Dashboard

The integration writes **hourly statistics** directly into Home Assistant's recorder (the same mechanism the official Opower integration uses). Unlike sensor-based data — which lumps each day's usage into whichever hour HA happened to poll — these statistics are backdated to the actual hour the energy was used, so hourly, daily, weekly, and monthly views are all correct.

Go to **Settings → Dashboards → Energy** and pick the APS **statistics** (they appear alongside sensors in the pickers; search for "APS"):

- **Grid consumption:** `APS Grid Import` (solar) or `APS Energy Consumption` (non-solar)
- **Return to grid** (solar): `APS Grid Export`
- **Solar production** (solar): `APS Solar Generation`

Home Assistant computes self-consumed solar automatically (production − export).

Notes:

- On first setup the integration backfills **30 days** of hourly history (one API request per day), so the initial refresh takes a minute or two. After that, only new days are fetched.
- APS publishes data with a **~1-day delay**, so "today" is always empty and yesterday appears once APS posts it (typically early morning). The last 2 days are re-fetched whenever new data arrives, so estimated readings APS later corrects get rewritten.
- If APS's hourly endpoint fails for a day, that day's total is recorded at midnight as a fallback — the day is still attributed correctly.
- The *Current Cycle* sensors still exist for dashboards and automations, but statistics are the recommended Energy Dashboard source. If you previously configured the cycle sensors, swap them for the statistics above (you can purge the old sensor-based history from **Developer Tools → Statistics** if desired).
- Numbers may differ slightly from solar-inverter apps (Tesla, Enphase, …): APS reports what its **revenue meter** records, while inverter hardware measures at a different point in the system — wiring losses, metering accuracy, hour-boundary alignment, and APS's estimated reads all contribute small gaps. The APS statistics are what you're actually billed on.

---

## Sensor Attributes

All energy sensors carry `account_id`, `premise_address`, `latest_data_date`, and `bill_cycle_start`. `sensor.aps_current_billing_cycle_kwh` adds `rate_plan` (e.g. `R3-47`). The balance sensor carries `due_date`, `new_charges`, `auto_pay`, `budget_billing`, and last-payment details.

---

## Lovelace Example

```yaml
type: entities
title: APS Energy
entities:
  - entity: sensor.aps_yesterday_kwh
    name: Yesterday
  - entity: sensor.aps_current_billing_cycle_kwh
    name: This Billing Cycle
  - entity: sensor.aps_30_day_kwh
    name: Last 30 Days
  - entity: sensor.aps_yesterday_on_peak_kwh
    name: On-Peak (Yesterday)
  - entity: sensor.aps_yesterday_off_peak_kwh
    name: Off-Peak (Yesterday)
  - entity: sensor.aps_current_balance
    name: Current Balance
  - entity: sensor.aps_bill_due_date
    name: Due Date
```

---

## Update Frequency

The integration polls APS **once per hour**. APS updates usage data daily (not real-time), so energy readings reflect usage through the **previous day**. Balance and billing data reflect your APS.com balance at the last poll. Hourly statistics data is only fetched when APS publishes a new day (plus a 2-day overlap for corrections), so most hourly polls make no extra API calls.

---

## Troubleshooting

### "Invalid Auth" error during setup
- Verify your credentials work at [aps.com](https://www.aps.com/en/Authorization/Login).
- APS rate-limits login attempts. Wait 5–10 minutes and try again.
- Use your **APS.com username** (not your email address or account number).

### Integration in "Setup Retry" / sensors unavailable
Check **Settings → System → Logs** and filter for `aps_usage`. Common causes:

| Error | Cause | Fix |
|-------|-------|-----|
| `Authentication failed` | Wrong password / rate limited | Re-check credentials; wait 10 min |
| `Connection error` | HA can't reach aps.com | Check HA network / DNS |
| `No active service agreement` | Unrecognized account structure | See below |
| `Login request blocked` | Imperva WAF challenge | Retry in 15 minutes (auto-recovers) |

### "No active service agreement found"
The integration handles many account layouts (multiple agreements, solar production meters, placeholder end dates, single-item responses). If yours still isn't recognized, the log will contain a warning starting with `APS: No service agreement (SASP) found` that includes the **key structure** of the API response (values stripped — no personal data). Please [open an issue](https://github.com/damianharouff/aps-csv-ha/issues) and paste that warning.

### Solar sensors unavailable
The solar endpoint is best-effort: if it fails, the core usage sensors keep working and the solar sensors go unavailable. Enable debug logging (below) and look for `APS: Solar usage API` or `no production meter` warnings, then open an issue with what you find.

### Statistics missing or a day looks wrong
Statistics failures never break the sensors — check the logs for `APS: statistics update failed` or (at debug level) `hourly … fetch failed`. A day recorded as a single midnight bar means the hourly endpoint had no data for it; it is rewritten automatically if APS publishes hourly data within the 2-day re-fetch window. To rebuild history from scratch, delete the `aps_usage:*` statistics in **Developer Tools → Statistics** and reload the integration — it will backfill 30 days again.

### Enable debug logging
Add to `configuration.yaml` and restart:
```yaml
logger:
  default: warning
  logs:
    custom_components.aps_usage: debug
```

---

## How It Works

This integration was reverse-engineered from the APS website (`aps.com`) and the Android mobile app (`com.aps.apsconsumerapp` v4.0.10, decompiled with jadx + hermes-dec).

### Authentication Flow
1. **Password encryption:** The password is encrypted with an RSA-2048 public key using PKCS#1 v1.5 (replicating the `JSEncrypt` library used by the APS website login form, key extracted from `aps-apscom.js`).
2. **Login:** `POST https://www.aps.com/api/sitecore/SitecoreReactApi/UserAuthentication` — returns `{isLoginSuccess: true, redirectUrl: "..."}`.
3. **Session establishment:** `GET {redirectUrl}` — establishes ASP.NET session cookies.
4. **Token retrieval:** `GET https://www.aps.com/api/sitecore/sitecorereactapi/GetAllUserDetails` — returns the Azure AD B2C access token (`B2C_AccessToken`), account details, and `getSASPListByAccountID` containing all service agreements with meter numbers.

### Service Agreement Selection
Every service agreement / service point (SASP) in the account is collected — tolerating single-item dict responses, key-casing differences, far-future placeholder end dates, and production-meter entries that carry no SA ID. The **active consumption agreement** is chosen (non-PROD service point, has an SA). Solar is detected the same way the APS dashboard does it: premise-level flags (`isProductionMeter` / `isBidirectionalMeter`) and a SASP entry with `sPType: "PROD"` — that PROD entry is the **production meter** used for solar data requests.

### Usage Data
```
GET https://mobi.aps.com/ccb-billing/v1/getdailyusagecharges
```
Query parameters: `action=read`, `accountNumber`, `userName`, `emailAddress`, `sAID` (Service Agreement ID), `spId` (Service Point ID), `startDate`, `endDate`, `cSSUser=APSCOM`. The response contains a `series` array (one entry per day) with `totalUsage`, `onPeakUsage`, `offPeakUsage`, temperature, and charge amounts, plus `billCycleDates` marking billing cycle boundaries.

### Hourly Usage Data
```
GET https://mobi.aps.com/ccb-billing/v1/gethourlyusagecharges
```
Same parameters and auth as the daily endpoint, but a single `date=YYYY-MM-DD` instead of a range. Each `series` item carries `readTime` (`"01:00 AM"`), `totalUsage`, the on/off-peak splits, and `hasEstimatedData`/`hasMissingData` flags; `periodicity` gives minutes per reading (usually 60). Used to backfill hourly long-term statistics.

### Solar Data (solar accounts)
```
POST https://mobi.aps.com/customerhistoryservices/v1/getsummarizedusagesolardata
```
JSON body includes both meters: `utilityMeterNumber`/`utilityMeterSPId` and `prodMeterNumber`/`prodMeterSPId`, plus `saId`, `premiseId`, `displayType` (`"D"` daily, `"H"` hourly, `"M"` monthly), a date range, and a `ratePlan` array. The response's `Series` array carries per-day `totalAPSEnergyUsed` (grid import), `totalPowerGenerated` (production), `totalGenerationSold` (export), and `totalGenerationUsed` (self-consumed), each with actual + estimated variants. For hourly requests, set both dates to the same day — the `date` field of each item then carries the hour label.

### Financial Data
Extracted directly from the `GetAllUserDetails` response — `getAccountFinancialDetails` contains `currentBalance`, `dueDt`, `lastPayAmt`, `lastPayDt`, and `newCharges`. No additional API call is needed.

---

## Privacy & Security

- Credentials are stored in **Home Assistant's encrypted config entry storage**. They are never logged or transmitted to any third party.
- All network requests go directly to `www.aps.com` and `mobi.aps.com`.
- The integration is **read-only** — it makes no changes to your APS account.
- Diagnostic log output strips values from API responses (key names only).

---

## Contributing

Pull requests are welcome! When reporting a bug, please include:
1. Your Home Assistant version (`Settings → About`)
2. The integration version
3. Relevant log entries (with **all credentials and account numbers redacted**)

---

## License

[MIT License](LICENSE)

---

## Credits & Disclaimer

Originally based on [Conexo-Casa/aps-csv-ha](https://github.com/Conexo-Casa/aps-csv-ha).

This integration is not affiliated with, endorsed by, or supported by Arizona Public Service Company (APS). It uses undocumented private APIs that APS may change at any time. Use at your own risk.
