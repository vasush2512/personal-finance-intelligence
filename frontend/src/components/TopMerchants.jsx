import { formatMoney } from "../format.js";

/**
 * Biggest merchants by total spend.
 *
 * A plain list, not a chart. Ten labelled values that the eye reads top to
 * bottom anyway gain nothing from bars, and the names are the content.
 */
export default function TopMerchants({ merchants }) {
  return (
    <div className="card">
      <h2>Top merchants</h2>

      {merchants.length === 0 ? (
        <p className="chart-note">Nothing to show yet.</p>
      ) : (
        merchants.map((merchant) => (
          <div className="merchant-row" key={merchant.merchant}>
            <div>
              <span className="merchant-name">{merchant.merchant}</span>
              <span className="merchant-count">×{merchant.count}</span>
            </div>
            <div className="merchant-total">{formatMoney(merchant.total)}</div>
          </div>
        ))
      )}

      <p className="chart-note">
        Grouped by the first word of the cleaned narration, so a few rows land
        under an odd name.
      </p>
    </div>
  );
}
