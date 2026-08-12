import { formatMoney } from "../format.js";

/**
 * The four headline numbers.
 *
 * Net is coloured because its sign is the point; the other three are not,
 * since "you spent a lot" is not an error state.
 */
export default function SummaryCards({ summary, scopeLabel }) {
  const net = Number(summary.net);

  return (
    <div className="cards">
      <div className="card">
        <div className="stat-label">Spent</div>
        <div className="stat-value">{formatMoney(summary.total_spent)}</div>
        <div className="stat-note">{scopeLabel}, transfers excluded</div>
      </div>

      <div className="card">
        <div className="stat-label">Income</div>
        <div className="stat-value">{formatMoney(summary.total_income)}</div>
        <div className="stat-note">{scopeLabel}</div>
      </div>

      <div className="card">
        <div className="stat-label">Net</div>
        <div className={`stat-value ${net < 0 ? "negative" : "positive"}`}>
          {formatMoney(summary.net)}
        </div>
        <div className="stat-note">Income minus spending</div>
      </div>

      <div className="card">
        <div className="stat-label">Transactions</div>
        <div className="stat-value">{summary.transaction_count}</div>
        <div className="stat-note">{scopeLabel}</div>
      </div>
    </div>
  );
}
