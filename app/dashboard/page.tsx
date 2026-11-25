"use client";

import { RiShieldCheckLine } from "@remixicon/react";

import { AppShell } from "@/components/application/app-shell/app-shell";
import { OrdersChartCard, type OrdersPoint } from "@/components/application/dashboard/orders-chart-card";
import { RevenueChartCard, type RevenuePoint } from "@/components/application/dashboard/revenue-chart-card";
import { StatCards } from "@/components/application/dashboard/stat-cards";
import { DataTableExample } from "@/components/application/data-table/data-table";

const LINES_HARDENED_DATA: RevenuePoint[] = [
  { label: "Jan", current: 2450, previous: 1620 },
  { label: "Feb", current: 2890, previous: 1840 },
  { label: "Mar", current: 3420, previous: 2150 },
  { label: "Apr", current: 3180, previous: 2310 },
  { label: "May", current: 3910, previous: 2540 },
  { label: "Jun", current: 4280, previous: 2780 },
  { label: "Jul", current: 4650, previous: 2920 },
  { label: "Aug", current: 4390, previous: 3040 },
  { label: "Sep", current: 4820, previous: 3180 },
  { label: "Oct", current: 5040, previous: 3340 },
  { label: "Nov", current: 4890, previous: 3210 },
  { label: "Dec", current: 5000, previous: 3490 },
];

const BUGS_CRUSHED_DATA: OrdersPoint[] = [
  { label: "Jan", current: 18, previous: 11 },
  { label: "Feb", current: 22, previous: 13 },
  { label: "Mar", current: 27, previous: 16 },
  { label: "Apr", current: 24, previous: 15 },
  { label: "May", current: 31, previous: 19 },
  { label: "Jun", current: 34, previous: 21 },
  { label: "Jul", current: 39, previous: 22 },
  { label: "Aug", current: 35, previous: 24 },
  { label: "Sep", current: 41, previous: 25 },
  { label: "Oct", current: 43, previous: 26 },
  { label: "Nov", current: 37, previous: 23 },
  { label: "Dec", current: 38, previous: 27 },
];

/**
 * Codely Security & Usage Flex Dashboard:
 * Vulnerabilities fixed, bugs crushed, lines changed to date, and security score.
 */
export default function DashboardPage() {
  return (
    <AppShell title="Dashboard" heading="Welcome ninad — Security & Usage" icon={RiShieldCheckLine}>
      <StatCards variant="footer" />

      <div className="flex w-full flex-col items-stretch gap-4 xl:flex-row">
        <RevenueChartCard title="Lines Hardened" prefix="" data={LINES_HARDENED_DATA} />
        <OrdersChartCard title="Bugs Crushed" data={BUGS_CRUSHED_DATA} />
      </div>

      <DataTableExample />
    </AppShell>
  );
}
