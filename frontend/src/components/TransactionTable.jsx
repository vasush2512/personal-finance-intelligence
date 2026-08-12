import { formatDate, formatMoneyExact, shortenDescription } from "../format.js";

const PAGE_SIZE = 50;

/**
 * The transaction list, with an inline category dropdown.
 *
 * Changing the dropdown PATCHes immediately — there is no save button,
 * because a correction is a single decision and a second click to confirm it
 * only creates a way to lose the change.
 *
 * The source tag matters: it tells you whether a keyword rule, the model, or
 * you yourself put that category there.
 */
export default function TransactionTable({
  page,
  categories,
  onChangeCategory,
  savingId,
  offset,
  onOffsetChange,
}) {
  const { items, total } = page;
  const showingFrom = total === 0 ? 0 : offset + 1;
  const showingTo = Math.min(offset + items.length, total);

  return (
    <div className="card">
      <h2>Transactions</h2>

      <div style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Description</th>
              <th>Category</th>
              <th className="amount">Amount</th>
            </tr>
          </thead>
          <tbody>
            {items.map((transaction) => (
              <tr key={transaction.id}>
                <td className="date">{formatDate(transaction.date)}</td>
                <td className="description" title={transaction.description}>
                  {shortenDescription(transaction.description)}
                </td>
                <td>
                  <select
                    value={transaction.category}
                    disabled={savingId === transaction.id}
                    onChange={(event) =>
                      onChangeCategory(transaction.id, event.target.value)
                    }
                  >
                    {categories.map((category) => (
                      <option key={category} value={category}>
                        {category}
                      </option>
                    ))}
                  </select>
                  <span className={`source-tag ${transaction.category_source}`}>
                    {transaction.category_source}
                    {transaction.category_source === "model" &&
                      transaction.confidence != null &&
                      ` ${Math.round(transaction.confidence * 100)}%`}
                  </span>
                </td>
                <td className="amount">
                  {transaction.direction === "credit" ? "+" : "−"}
                  {formatMoneyExact(transaction.amount)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {items.length === 0 && (
        <p className="chart-note">No transactions match these filters.</p>
      )}

      <div className="pagination">
        <button
          disabled={offset === 0}
          onClick={() => onOffsetChange(Math.max(0, offset - PAGE_SIZE))}
        >
          Previous
        </button>
        <button
          disabled={showingTo >= total}
          onClick={() => onOffsetChange(offset + PAGE_SIZE)}
        >
          Next
        </button>
        <span>
          Showing {showingFrom}–{showingTo} of {total}
        </span>
      </div>
    </div>
  );
}

export { PAGE_SIZE };
