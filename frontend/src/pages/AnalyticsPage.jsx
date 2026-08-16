import ExportMenu from "../components/ExportMenu.jsx";
import { CategoryChart, TrendChart } from "../components/LazyCharts.jsx";
import { decodeSource } from "../components/Filters.jsx";
import InsightsPanel from "../components/InsightsPanel.jsx";
import TopMerchants from "../components/TopMerchants.jsx";
import { StatCard } from "../components/StatCard.jsx";
import Card, { CardHead, CardFoot } from "../components/ui/Card.jsx";
import { IconChart, IconTrendDown, IconTrendUp, IconWallet } from "../icons.jsx";
import { formatCategory, formatMoney, formatMonth, toNumber } from "../format.js";

/**
 * The deeper read: trends over time, the full category split, and merchants.
 *
 * Everything here is derived from /api/summary and /api/trends — the same two
 * responses the dashboard uses. Nothing is invented: where a figure would need
 * data the backend does not return (month-on-month change per category, for
 * instance), it is simply not shown rather than approximated.
 */
export default function AnalyticsPage({
  summary,
  trends,
  scopeLabel,
  month,
  source,
  dataVersion,
  onError,
  onSuccess,
}) {
  const insights = deriveInsights(summary, trends);

  return (
    <div className="stack">
      <div className="grid-4">
        <StatCard
          label="Average monthly spend"
          value={insights.averageSpend ? formatMoney(insights.averageSpend) : "—"}
          note={`Across ${trends.length} month${trends.length === 1 ? "" : "s"} of data`}
          icon={IconTrendDown}
        />
        <StatCard
          label="Highest spending month"
          value={insights.peak ? formatMonth(insights.peak.month) : "—"}
          note={insights.peak ? formatMoney(insights.peak.spent) : "No data yet"}
          icon={IconChart}
          tone="primary"
        />
        <StatCard
          label="Biggest category"
          value={
            insights.topCategory
              ? formatCategory(insights.topCategory.category)
              : "—"
          }
          note={
            insights.topCategory
              ? `${formatMoney(insights.topCategory.total)} · ${insights.topCategoryShare}% of spending`
              : "No data yet"
          }
          icon={IconWallet}
        />
        <StatCard
          label="Savings rate"
          value={insights.savingsRate === null ? "—" : `${insights.savingsRate}%`}
          note={
            insights.savingsRate === null
              ? "Needs recorded income"
              : "Share of income not spent"
          }
          icon={IconTrendUp}
          tone={insights.savingsRate !== null && insights.savingsRate < 0 ? "danger" : "success"}
        />
      </div>

      <InsightsPanel month={month} source={source} dataVersion={dataVersion} />

      <TrendChart
        trends={trends}
        variant="area"
        title="Spending over time"
        description="Money out against money in, month by month"
      />

      <div className="grid-2">
        <CategoryChart categories={summary.by_category} />
        <TopMerchants merchants={summary.top_merchants} />
      </div>

      <Card>
        <CardHead
          title="Category breakdown"
          description={`${scopeLabel}, transfers excluded`}
          bordered
          actions={
            <ExportMenu
              kind="summary"
              params={{ month, ...decodeSource(source) }}
              scopeLabel="Excel has categories, months and merchants"
              onError={onError}
              onSuccess={onSuccess}
            />
          }
        />
        <div className="table-wrap">
          <table className="cards-on-mobile">
            <thead>
              <tr>
                <th>Category</th>
                <th className="right">Transactions</th>
                <th className="right">Total</th>
                <th className="right">Share of spending</th>
                <th className="right">Average</th>
              </tr>
            </thead>
            <tbody>
              {summary.by_category.map((row) => {
                const total = toNumber(row.total);
                const share = insights.totalSpent
                  ? (total / insights.totalSpent) * 100
                  : 0;

                return (
                  <tr key={row.category}>
                    <td data-label="Category">{formatCategory(row.category)}</td>
                    <td className="num right" data-label="Transactions">
                      {row.count.toLocaleString("en-IN")}
                    </td>
                    <td className="num right" data-label="Total">
                      {formatMoney(row.total)}
                    </td>
                    <td className="num right" data-label="Share">
                      {share.toFixed(1)}%
                    </td>
                    <td className="num right" data-label="Average">
                      {formatMoney(total / (row.count || 1))}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <CardFoot>
          Shares are of total spending, not of all transactions — income and
          transfers are excluded from both the numerator and the denominator.
        </CardFoot>
      </Card>
    </div>
  );
}

/**
 * Figures the API does not return, computed from figures it does.
 *
 * Kept in one function so it is obvious exactly what is derived and from what.
 * Anything that cannot be derived honestly returns null and the card shows an
 * em dash rather than a confident zero.
 */
function deriveInsights(summary, trends) {
  const totalSpent = toNumber(summary.total_spent);
  const totalIncome = toNumber(summary.total_income);

  const peak = trends.reduce(
    (max, point) =>
      !max || toNumber(point.spent) > toNumber(max.spent) ? point : max,
    null
  );

  const topCategory = summary.by_category[0] || null;

  return {
    totalSpent,
    averageSpend: trends.length ? totalSpent / trends.length : 0,
    peak,
    topCategory,
    topCategoryShare: topCategory
      ? ((toNumber(topCategory.total) / (totalSpent || 1)) * 100).toFixed(0)
      : "0",
    // Meaningless without income on record, so say so instead of showing 100%.
    savingsRate:
      totalIncome > 0
        ? Math.round(((totalIncome - totalSpent) / totalIncome) * 100)
        : null,
  };
}
