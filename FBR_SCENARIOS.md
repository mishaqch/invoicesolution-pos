# FBR / PRAL Scenarios — Sale Type & Tax Rate Reference

Authoritative cross-reference of every PRAL sandbox scenario (`SN001`–`SN028`),
the `saleType` string it requires, and the tax rate it uses. Generated from the
code — the source of truth is:

- **Scenario titles + builders:** [`backend/apps/fbr/scenarios.py`](backend/apps/fbr/scenarios.py) (`KNOWN_SCENARIO_META`, `build_snXXX`)
- **Sale-type strings:** [`backend/apps/fbr/sale_types.py`](backend/apps/fbr/sale_types.py) (must match PRAL `/pdi/v1/transtypecode` verbatim)
- **UoM strings:** [`backend/apps/fbr/builder.py`](backend/apps/fbr/builder.py) (`UOM_FBR_MAP`)
- **Scenario auto-selection:** [`backend/apps/fbr/scenarios.py`](backend/apps/fbr/scenarios.py) (`pick_scenario_id`)

> **How scenarios work.** In **sandbox**, PRAL assigns each taxpayer a set of
> scenario IDs; every invoice line's `saleType` must be compatible with the
> `scenarioId` sent, or PRAL rejects with `0204` ("Sale type not match with
> provided scenario"). In **production** there is **no `scenarioId`** — PRAL
> classifies each line by its `saleType` alone. The app picks the sandbox
> scenario automatically from the invoice's contents (see *Auto-selection*
> below); the rate is whatever the operator sets on the line (it must be one
> PRAL allows for that saleType).

---

## The table

| Scenario | Title | `saleType` (exact) | Tax rate | Notes |
|---|---|---|---|---|
| **SN001** | Standard Rate Goods → Registered Buyers | `Goods at standard rate (default)` | **18%** | B2B, input-tax-credit eligible |
| **SN002** | Standard Rate Goods → Unregistered Buyers | `Goods at standard rate (default)` | **18%** | Walk-in / B2C |
| **SN003** | Steel (Melted / Re-Rolled) | `Steel melting and re-rolling` | 18% | Sector-specific |
| **SN004** | Steel Scrap by Ship Breakers | `Ship breaking` | 18% | |
| **SN005** | Reduced Rate Goods (8th Schedule) | `Goods at Reduced Rate` | **1%** | 8th Schedule |
| **SN006** | Exempt Goods (6th Schedule) | `Exempt goods` | **Exempt** | rate = literal `"Exempt"`, **not** `"0%"` |
| **SN007** | Zero-Rated Goods (5th Schedule) | `Goods at zero-rate` | **0%** | 5th Schedule |
| **SN008** | 3rd Schedule Goods | `3rd Schedule Goods` | **18%** | tax computed **on retail/MRP** |
| **SN009** | Purchase from Cotton Ginners | `Cotton ginners` | 18% | |
| **SN010** | Telecom Services by Mobile Operators | `Telecommunication services` | **17%** | |
| **SN011** | Steel via Toll Manufacturing | `Toll Manufacturing` | 18% | |
| **SN012** | Petroleum Products | `Petroleum Products` | **1.43%** | |
| **SN013** | Electricity to Retailers | `Electricity Supply to Retailers` | **5%** | |
| **SN014** | Gas to CNG Stations | `Gas to CNG stations` | 18% | |
| **SN015** | Mobile Phones | `Mobile Phones` | **18%** | |
| **SN016** | Processing / Conversion of Goods | `Processing/Conversion of Goods` | **5%** | |
| **SN017** | Goods (FED in ST Mode) | `Goods (FED in ST Mode)` | **8%** | |
| **SN018** | Services (FED in ST Mode) | `Services (FED in ST Mode)` | **8%** | |
| **SN019** | **Services (ICT Ordinance)** | **`Services`** | **16%** (also 0/Exempt/5/15/17%) | see *Services* below — **NOT 18%** |
| **SN020** | Electric Vehicles | `Electric Vehicle` | **1%** | SRO: `6th Schd Table III` |
| **SN021** | Cement / Concrete Block | `Cement /Concrete Block` | **Rs.3 per unit** | fixed per-unit |
| **SN022** | Potassium Chlorate | `Potassium Chlorate` | **18% + Rs.60/kg** | mixed |
| **SN023** | CNG Sales | `CNG Sales` | **Rs.200/unit** | SRO: `581(1)/2024` |
| **SN024** | Goods per SRO 297(I)/2023 | `Goods as per SRO.297(⏐)/2023` | **25%** | ⚠️ saleType uses a **pipe `\|`**, not letter I |
| **SN025** | Drugs (8th Schedule Serial 81) | `Non-Adjustable Supplies` | **0%** | SRO: `EIGHTH SCHEDULE Table 1` |
| **SN026** | Standard Rate → End Consumers (Retail) | `Goods at standard rate (default)` | **18%** | retail variant of SN002 |
| **SN027** | 3rd Schedule → End Consumers (Retail) | `3rd Schedule Goods` | **18%** | tax on retail; retail variant of SN008 |
| **SN028** | Reduced Rate → End Consumers (Retail) | `Goods at Reduced Rate` | **1%** | SRO: `EIGHTH SCHEDULE Table 1` |

---

## Services (SN019) — the important one for service providers

Services HS codes live under **chapter 98** (`98xx.xxxx`), e.g. `9819.1300`
(Commission Agents). A services line has **three** requirements that differ
from goods, all confirmed against the live PRAL sandbox validator:

| Field | Goods (wrong for services) | **Services (correct)** |
|---|---|---|
| `saleType` | `Goods at standard rate (default)` | **`Services`** |
| `uoM` | `Numbers, pieces, units` | **`Others`** |
| `scenarioId` (sandbox) | `SN002` | **`SN019`** |
| `rate` | `18%` | **16%** (valid: 0% / Exempt / 5% / 15% / 16% / 17%) |

Getting any one wrong yields, respectively: `0099` (UoM not allowed for HS),
`0204` (sale type / scenario mismatch), `0046` (rate not valid for sale type).

**The app now handles the first three automatically** (see *Auto-selection*):
when a chapter-98 HS code is used, it sends `saleType = Services`, `uoM =
Others`, and picks `SN019`. **The operator must still choose a services-valid
rate** — pick **"Services 16%"** (or 15%) from the tax-rate dropdown; **18% is
rejected for services.**

---

## Rates that are NOT a simple percentage

Some scenarios use fixed or mixed rates handled by their scenario builders, not
the plain "%" dropdown:

- **SN021** — `Rs.3 per unit` (fixed per unit)
- **SN023** — `Rs.200/unit` (fixed per unit)
- **SN022** — `18% + Rs.60/kg` (ad-valorem + specific)
- **SN012** — `1.43%` (petroleum)

## 3rd-Schedule math (SN008 / SN027)

For 3rd-Schedule (retail-price-fixed) lines, sales tax is charged **ON the MRP**
for the given rate, not extracted tax-inclusive:

```
fixedNotifiedValueOrRetailPrice = retail_price × qty
salesTaxApplicable              = retail_total × rate / 100
valueSalesExcludingST           = retail_total          # full MRP (PRAL rejects 0/empty)
totalValues                     = retail_total + salesTaxApplicable
```

---

## Auto-selection (`pick_scenario_id`)

In **sandbox**, the app derives the `scenarioId` from the whole invoice
(production sends none). All-lines-of-a-kind → that scenario; otherwise the
standard fallback:

| Invoice content | Scenario picked |
|---|---|
| All **exempt** lines (`Exempt goods`) | `SN006` *(if assigned)* |
| All **zero-rate** lines (`Goods at zero-rate`) | `SN007` *(if assigned)* |
| All **3rd-Schedule** lines (`fixedNotifiedValueOrRetailPrice > 0`) | `SN027` (walk-in, if assigned) else `SN008` |
| All **reduced-rate** lines (8th Schedule) | `SN028` (walk-in, if assigned) else `SN005` |
| All **services** lines (HS ch. 98 / `saleType = Services`) | **`SN019`** |
| **Registered** buyer, standard goods | `SN001` |
| **Unregistered** buyer, standard goods | `SN026` (retail, if assigned) else `SN002` |

Retail end-consumer scenarios (`SN026/27/28`) are only used for **walk-in
(unregistered)** buyers **and** only when the tenant is actually assigned that
code in IRIS. Otherwise the app falls back to the non-retail equivalent.

---

## Gotchas (from `INTEGRATIONS.md` / the code)

- **`rate` is a string** like `"18%"`, not a number. Exempt sends the literal
  `"Exempt"`.
- **`uoM` is a verbose enum string** — `"KG"` not `"Kilograms"`, `"Numbers,
  pieces, units"` for each, `"Others"` for services. See `UOM_FBR_MAP`.
- **`saleType` must match `/pdi/v1/transtypecode` verbatim**, including the
  pipe character in SN024.
- **`scenarioId` is sandbox-only** — omitted in production.
- The **sandbox test rates** in `build_snXXX` are the canonical rate for each
  scenario; a real invoice's rate is set per line and must be one PRAL allows
  for that `saleType` (query `/pdi/v1/SaleTypeToRate` for the exact list).
