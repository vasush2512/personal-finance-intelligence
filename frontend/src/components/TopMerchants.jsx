import { formatMoney, toNumber } from "../format.js";
import Card, { CardHead, ChartNote } from "./ui/Card.jsx";
import { EmptyState } from "./ui/Feedback.jsx";

/**
 * Biggest merchants by total spend.
 *
 * A ranked list with a proportion bar, not a chart. Ten labelled values the
 * eye reads top to bottom gain nothing from axes — but they do gain from being
 * able to see at a glance that the top one is twice the second, so each row
 * carries a bar scaled against the largest.
 */
export default function TopMerchants({ merchants }) {
  const largest = merchants.reduce(
    (max, merchant) => Math.max(max, toNumber(merchant.total)),
    0
  );

  return (
    <Card>
      <CardHead
        title="Top merchants"
        description="By total spend in the selected period"
        bordered
      />

      {merchants.length === 0 ? (
        <EmptyState
          title="No merchants yet"
          description="Import a statement and the biggest merchants appear here."
        />
      ) : (
        merchants.map((merchant, index) => (
          <div className="list-row" key={merchant.merchant}>
            <span className="rank">{index + 1}</span>

            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: "var(--sp-3)",
                }}
              >
                <span className="merchant-name">{merchant.merchant}</span>
                <span
                  className="num"
                  style={{ fontWeight: 560, whiteSpace: "nowrap" }}
                >
                  {formatMoney(merchant.total)}
                </span>
              </div>

              <div className="bar-track">
                <div
                  className="bar-fill"
                  style={{
                    width: `${
                      largest ? (toNumber(merchant.total) / largest) * 100 : 0
                    }%`,
                  }}
                />
              </div>

              <div className="tile-meta" style={{ marginTop: 3 }}>
                {merchant.count} transaction{merchant.count === 1 ? "" : "s"}
              </div>
            </div>
          </div>
        ))
      )}

      <ChartNote>
        Grouped by the first word of the cleaned narration, so a few rows land
        under an odd name.
      </ChartNote>
    </Card>
  );
}
