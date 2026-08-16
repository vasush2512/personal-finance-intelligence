import { Suspense, lazy } from "react";

import { ChartSkeleton } from "./ui/Feedback.jsx";

/**
 * The charts, loaded only when a page that has one is opened.
 *
 * Recharts and its d3 dependencies are about 300 kB — half the entire bundle —
 * and only two of the eleven pages draw a chart. Imported normally, everyone
 * pays for them on first load, including someone who only ever opens
 * Transactions.
 *
 * The fallback is the same skeleton the page uses while its data is in flight,
 * so a slow network shows one consistent loading state rather than a gap that
 * suddenly fills.
 *
 * Both are wrapped here rather than at each call site so no page can forget
 * the Suspense boundary — a lazy component without one throws.
 */
const CategoryChartInner = lazy(() => import("./CategoryChart.jsx"));
const TrendChartInner = lazy(() => import("./TrendChart.jsx"));

export function CategoryChart(props) {
  return (
    <Suspense fallback={<ChartSkeleton height={240} />}>
      <CategoryChartInner {...props} />
    </Suspense>
  );
}

export function TrendChart(props) {
  return (
    <Suspense fallback={<ChartSkeleton height={260} />}>
      <TrendChartInner {...props} />
    </Suspense>
  );
}
