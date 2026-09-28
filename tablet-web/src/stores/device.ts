import { create } from "zustand";
import { persist } from "zustand/middleware";

import { getDeviceFingerprint } from "@/lib/pairing";
import type { PairResponse } from "@/types";

interface DeviceState {
  terminalId: string | null;
  branchId: string | null;
  branchName: string | null;
  tenantName: string | null;
  deviceFingerprint: string;
  sdcUrl: string | null;

  /** Store the result of a successful pairing. */
  setPaired: (r: PairResponse) => void;
  /** Un-pair the device entirely (returns to /pairing). */
  unpair: () => void;
}

export const useDeviceStore = create<DeviceState>()(
  persist(
    (set) => ({
      terminalId: null,
      branchId: null,
      branchName: null,
      tenantName: null,
      // Generated once, reused for every pair/roster call.
      deviceFingerprint: getDeviceFingerprint(),
      sdcUrl: null,

      setPaired: (r) =>
        set({
          terminalId: r.terminal_id,
          branchId: r.branch_id,
          branchName: r.branch_name,
          tenantName: r.tenant_name,
          sdcUrl: r.sdc_url ?? null,
        }),

      unpair: () =>
        set({
          terminalId: null,
          branchId: null,
          branchName: null,
          tenantName: null,
          sdcUrl: null,
        }),
    }),
    {
      name: "tablet-device",
      partialize: (s) => ({
        terminalId: s.terminalId,
        branchId: s.branchId,
        branchName: s.branchName,
        tenantName: s.tenantName,
        deviceFingerprint: s.deviceFingerprint,
        sdcUrl: s.sdcUrl,
      }),
    },
  ),
);
