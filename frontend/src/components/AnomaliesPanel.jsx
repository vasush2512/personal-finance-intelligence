import { formatDate, formatMoneyExact, shortenDescription } from "../format.js";

/**
 * Unusually large spending, with the reason spelled out.
 *
 * The reason string is the whole point of this panel. "Rs 9,400.00 on food —
 * 23.0x your usual Rs 409.00" tells you what to go look at; a red exclamation
 * mark tells you nothing and trains you to ignore it.
 *
 * A flag is not an accusation. A genuinely large dinner is unusual and also
 * fine, which is why nothing here is styled as an error.
 */
export default function AnomaliesPanel({ anomalies }) {
  return (
    <div className="card">
      <h2>Unusual spending</h2>

      {anomalies.length === 0 ? (
        <p className="chart-note">
          Nothing out of the ordinary. A transaction is flagged when it is far
          above the usual for its category, and only once that category has at
          least eight earlier transactions to compare against.
        </p>
      ) : (
        <>
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Description</th>
                  <th className="amount">Amount</th>
                  <th>Why it stands out</th>
                </tr>
              </thead>
              <tbody>
                {anomalies.map((anomaly) => (
                  <tr key={anomaly.id}>
                    <td className="date">{formatDate(anomaly.date)}</td>
                    <td className="description" title={anomaly.description}>
                      {shortenDescription(anomaly.description, 38)}
                    </td>
                    <td className="amount">{formatMoneyExact(anomaly.amount)}</td>
                    <td>{anomaly.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="chart-note">
            Flagged when an amount exceeds the category average by more than
            2.5 standard deviations, over the trailing six months. Unusual does
            not mean wrong — a big dinner is both.
          </p>
        </>
      )}
    </div>
  );
}
