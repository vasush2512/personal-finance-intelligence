import CategoryChart from "../components/CategoryChart.jsx";
import SummaryCards from "../components/SummaryCards.jsx";
import TopMerchants from "../components/TopMerchants.jsx";
import TrendChart from "../components/TrendChart.jsx";
import { formatMonth } from "../format.js";
import { navigate } from "../router.js";

/**
 * The landing page: how much, on what, over time.
 *
 * Clicking a category bar filters the transaction list and takes you there,
 * because "food is my biggest category" is a question whose next step is
 * always "which transactions".
 */
export default function OverviewPage({ summary, trends, filters, onFilterChange }) {
  return (
    <>
      <SummaryCards
        summary={summary}
        scopeLabel={filters.month ? formatMonth(filters.month) : "All time"}
      />

      <TrendChart trends={trends} />

      <div className="grid-2">
        <CategoryChart
          categories={summary.by_category}
          selected={filters.category}
          onSelect={(category) => {
            onFilterChange({
              ...filters,
              category: filters.category === category ? "" : category,
            });
            navigate("/transactions");
          }}
        />
        <TopMerchants merchants={summary.top_merchants} />
      </div>
    </>
  );
}
