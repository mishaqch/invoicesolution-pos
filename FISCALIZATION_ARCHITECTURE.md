# Fiscalization Architecture — Cloud APIs, no local SDC (verified)

**Goal:** never install a fiscalization component (FBR SDC / PRA IMS) on a
tenant's Windows machine. Fiscalize every invoice from **our central server**
via each authority's **cloud API + per-taxpayer Bearer token**.

> Conclusions below are from two adversarially-verified deep-research passes over
> FBR/PRAL/PRA official technical specs + SROs, cross-referenced with our code
> (`backend/apps/fbr/client.py`, `sdc_client.py`, `tasks.py`).

---

## TL;DR

| Authority | Cloud fiscalization? | Endpoint | Auth | Reachable from our server? |
|---|---|---|---|---|
| **FBR** (federal) | **YES** — Digital Invoicing (DI) API | `https://gw.fbr.gov.pk/di_data/v1/di/postinvoicedata` | per-taxpayer **Bearer token** | ✅ **YES** (HTTP 401 + cert; IP already whitelisted) |
| **PRA** (Punjab) | **YES** — cloud IMS | `https://ims.pral.com.pk/ims/production/api/Live/PostData` | per-taxpayer **Bearer token** | ❌ TLS dropped — needs PRA IP-whitelisting |

**Both authorities offer a token-based cloud API. The local SDC/IMS Windows
service is NOT required for either.** Our app already implements both clients.

---

## 1. FBR — the cloud path (Digital Invoicing API)

**Verified (high confidence, FBR official DI technical specs):**

- FBR's **Digital Invoicing (DI) API** is a genuine server-to-server HTTPS
  endpoint: POST invoice JSON → get an **FBR-issued Invoice Number** (e.g.
  `7000007DI1747119701593`) + `statusCode:"00" Valid` + tracking number in real
  time, printed with the QR. **No SDC / localhost:8524 anywhere in the spec.**
- **Endpoint:** `https://gw.fbr.gov.pk/di_data/v1/di/postinvoicedata`
  (sandbox `…/postinvoicedata_sb`; routing by token). An older FMCG/POS family
  also exists: `…/pdi/v1/api/DigitalInvoicing/PostInvoiceData_v1`.
- **Auth:** per-taxpayer **`Authorization: Bearer <token>`**, issued by PRAL at
  registration on `e.fbr.gov.pk`, ~5-year validity.
- **Cloud servers** are onboarded by **IP whitelisting** (NTN + server public
  IP, up to 3 IPs) — not by installing anything local. **Our server IP is
  already FBR-whitelisted.**
- **POS is explicitly supported:** DI registration offers a **"Cloud Based /
  Client Server"** POS type and issues a POS registration number + Security
  Token; retailers are listed operators.

**Legal basis (2025 unification):** **SRO 69(I)/2025** replaced Chapter XIV of
the Sales Tax Rules 2006 with ONE framework (rule 150Q) that folds the old POS
Tier-1 regime (SRO 1006(I)/2021) and Digital Invoicing together. **SRO
1413(I)/2025** mandates integration **"through a licensed integrator or PRAL"**
against FBR's central system — a cloud/server model, not per-machine. Existing
POS-integrated retailers are deemed integrated under the new rules.

*Caveat (medium confidence):* no single FBR doc says verbatim "DI replaces the
SDC for POS Tier-1." The equivalence rests on the 2025 legal unification + the
DI spec's own Cloud-Based POS type — an inference across documents.

**Live check from our server:**
`POST gw.fbr.gov.pk/di_data/v1/di/postinvoicedata_sb` → **HTTP 401** ("send a
token") and the FBR cert is presented → **the endpoint is fully reachable; it
just needs a valid token.** (Contrast: PRA's `ims.pral.com.pk` drops the TLS
handshake entirely.)

### What this means for our FBR POS tenants (e.g. PEER TRADERS)

PEER TRADERS is currently `ims_sdc` (would need the local Windows SDC). To move
it to cloud — **no new integration to build, our DI-API client already does
this**:

1. Register the POS on `e.fbr.gov.pk` (POS type = **Cloud Based**) → get the
   **DI Bearer token** for the taxpayer.
2. Set the tenant's `fbr_connection_type = "di_api"`.
3. Store the DI Bearer token (production) via the FBR setup UI → the same
   `FbrToken` model + `FbrClient` we already use for Digital Invoicing tenants.
4. Our `tasks.submit_invoice_to_fbr` DI-API path posts to
   `gw.fbr.gov.pk/di_data/v1/di/postinvoicedata` with the Bearer token, gets the
   fiscal number + QR back → prints on the receipt. **Done. No SDC.**

> Nuance: FBR POS may still involve `scenarioId` in sandbox; production
> classifies per-line by `saleType`. Our builder + `pick_scenario_id` already
> handle this. A POS/retail invoice uses standard saleType + the buyer's
> registration type, same as our existing DI flow.

---

## 2. PRA — the cloud path (already built)

- **Endpoint:** `https://ims.pral.com.pk/ims/{sandbox|production}/api/Live/PostData`
- **Auth:** per-taxpayer **Bearer token** + **POS ID** in the body.
- **Blocker:** PRA's cloud **drops our TLS handshake** (SSLEOFError) from our
  server AND an independent IP → PRA-side gate. **FBR whitelisting does NOT
  carry to PRA** (separate infra, `103.125.60.124` vs FBR's gw). Needs PRA to
  whitelist our server IP `167.233.19.109` (email `eims@pra.punjab.gov.pk` with
  PNTN + POS ID + Server IP).
- Code: `pra_cloud` connection type, `sdc_client.submit_invoice_cloud`, routed in
  `tasks.py`. Deploy-ready; switches on the moment PRA opens access.

---

## 3. Can ONE SDC serve MANY taxpayers per-request? — NO (settled)

The earlier idea ("one central SDC, POS ID per request, serves everyone") is
**not supported** and is superseded by the cloud APIs above. Verified:

- The **local SDC/IMS is bound to ONE POS registration at install** (POS ID +
  Access Code entered once, stored locally). The local `:8524` POST has **no
  per-request auth** — `POSID` is a data field, not a swappable credential. So
  one local SDC ≠ multi-tenant router.
- **Per-request Bearer tokens exist only on the CLOUD endpoints** (FBR DI + PRA
  cloud) — and each token is per-taxpayer. That IS the multi-tenant model:
  **one codebase, many tenants, each with its own token.** ← what we do.
- Pakistan's sanctioned "one vendor → many taxpayers" is the **Licensed
  Integrator** model (SRO 69(I)/2025; roster incl. PRAL free integration) — a
  regulatory framework for WHO integrates, layered on top of the per-taxpayer
  cloud tokens.

---

## 4. Recommended architecture (both authorities, no SDC)

```
Terminal (rings sale, no fiscal component installed)
   │ syncs to our server
   ▼
Our Django server  ──per-tenant Bearer token──►  FBR DI-API  (gw.fbr.gov.pk)   ✅ reachable
                   └─per-tenant Bearer token──►  PRA cloud   (ims.pral.com.pk) ⏳ needs PRA whitelist
   ▼
stores fiscal number + QR on the invoice → prints on receipt
```

- **No SDC/IMS on any tenant or terminal machine.**
- **FBR POS tenants → `di_api`** (cloud), token per taxpayer. Works today.
- **PRA POS tenants → `pra_cloud`**, token per taxpayer. Works once PRA
  whitelists our IP.
- Non-fiscal tenants (e.g. TDCP) → `none`, unchanged.

### Action items

| # | Item | Owner | Status |
|---|---|---|---|
| 1 | FBR DI-API client (Bearer, gw.fbr.gov.pk) | code | ✅ already built |
| 2 | PRA cloud client (Bearer, ims.pral.com.pk) | code | ✅ built, deployed |
| 3 | Move PEER TRADERS: `ims_sdc` → `di_api` + add DI token | ops (self-service UI) | ▶ do when the taxpayer's DI token is available |
| 4 | Get PRA to whitelist server IP for `ims.pral.com.pk` | you → PRA | ⏳ email eims@pra.punjab.gov.pk |
| 5 | Retire the local-SDC path (`FBR_SDC_BASE_URL`) once all POS tenants are on cloud | code | later |

**Bottom line:** we do NOT need to host any SDC. Both FBR and PRA POS fiscalize
via cloud + per-taxpayer token from our central server — exactly the model we've
already implemented. FBR is reachable now; PRA needs an IP-whitelist email.
