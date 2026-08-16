import { IconCheckCircle } from "../icons.jsx";
import { formatDate, formatMoneyExact, shortenDescription } from "../format.js";
import Card, { CardHead, ChartNote } from "./ui/Card.jsx";
import Badge from "./ui/Badge.jsx";
import { EmptyState } from "./ui/Feedback.jsx";

/**
 * Unusually large spending, with the reason spelled out.
 *
 * The reason string is the whole point of this panel. "Rs 9,400.00 on food —
 * 23.0x your usual Rs 409.00" tells you what to go look at; a red exclamation
 * mark tells you nothing and trains you to ignore it.
 *
 * A flag is not an accusation. A genuinely large dinner is unusual and also
 * fine, which is why nothing here is styled as an error — the badge is amber,
 * not red, and the empty state is the reassuring one.
 */
export default function AnomaliesPanel({ anomalies, limit }) {
  const rows = limit ? anomalies.slice(0, limit) : anomalies;

  return (
    <Card>
      <CardHead
        title="Unusual spending"
        description={
          anomalies.length > 0
            ? `${anomalies.length} transaction${anomalies.length === 1 ? "" : "s"} stand out`
            : undefined
        }
        bordered
      />

      {anomalies.length === 0 ? (
        <EmptyState
          icon={IconCheckCircle}
          title="Nothing out of the ordinary"
          description="A transaction is flagged when it is far above the usual for its category, and only once that category has at least eight earlier transactions to compare against."
        />
      ) : (
        <>
          <div className="table-wrap">
            <table className="cards-on-mobile">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Description</th>
                  <th className="right">Amount</th>
                  <th>Why it stands out</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((anomaly) => (
                  <tr key={anomaly.id}>
                    <td className="date" data-label="Date">
                      {formatDate(anomaly.date)}
                    </td>
                    <td
                      className="desc"
                      data-label="Description"
                      title={anomaly.description}
                    >
                      {shortenDescription(anomaly.description, 40)}
                    </td>
                    <td className="num right" data-label="Amount">
                      <span className="amount-out">
                        {formatMoneyExact(anomaly.amount)}
                      </span>
                    </td>
                    <td data-label="Why">
                      <Badge tone="warning">{anomaly.reason}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <ChartNote>
            Flagged when an amount exceeds its category average by more than 2.5
            standard deviations over the trailing six months. Unusual does not
            mean wrong — a big dinner is both.
          </ChartNote>
        </>
      )}
    </Card>
  );
}
