import { categoryEmoji, IconInbox } from "../icons.jsx";
import {
  formatCategory,
  formatDate,
  formatMoneyExact,
  shortenDescription,
} from "../format.js";
import Card, { CardHead } from "./ui/Card.jsx";
import { SourceBadge } from "./ui/Badge.jsx";
import Button from "./ui/Button.jsx";
import { EmptyState } from "./ui/Feedback.jsx";

const PAGE_SIZE = 50;

/**
 * The transaction list, with an inline category dropdown.
 *
 * Changing the dropdown PATCHes immediately — there is no save button, because
 * a correction is a single decision and a second click to confirm it only
 * creates a way to lose the change. The row shows a spinner while the request
 * is in flight and the select is disabled, so the state is never ambiguous.
 *
 * The source badge matters: it tells you whether a keyword rule, the model, or
 * you yourself put that category there.
 *
 * On a phone the table becomes one card per row (see `.cards-on-mobile`), with
 * each cell labelled by its column. A four-column table on a 360px screen is
 * technically responsive and practically unusable.
 */
export default function TransactionTable({
  page,
  categories,
  onChangeCategory,
  savingId,
  offset,
  onOffsetChange,
  onClearFilters,
  isFiltered,
  onOpen,
}) {
  const { items, total } = page;
  const showingFrom = total === 0 ? 0 : offset + 1;
  const showingTo = Math.min(offset + items.length, total);

  return (
    <Card>
      <CardHead
        title="Transactions"
        description={
          total > 0
            ? `${total.toLocaleString("en-IN")} matching row${total === 1 ? "" : "s"}`
            : undefined
        }
        bordered
      />

      {items.length === 0 ? (
        <EmptyState
          icon={IconInbox}
          title={isFiltered ? "No matching transactions" : "No transactions yet"}
          description={
            isFiltered
              ? "No rows match these filters. Try widening them or clearing them entirely."
              : "Upload a bank statement to start analysing your spending."
          }
          action={
            isFiltered ? (
              <Button variant="secondary" onClick={onClearFilters}>
                Clear filters
              </Button>
            ) : (
              <Button variant="primary" onClick={() => (window.location.hash = "/upload")}>
                Upload statement
              </Button>
            )
          }
        />
      ) : (
        <>
          <div className="table-wrap">
            <table className="cards-on-mobile">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Merchant</th>
                  <th>Category</th>
                  <th>Labelled by</th>
                  <th className="right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {items.map((transaction) => {
                  const saving = savingId === transaction.id;
                  const credit = transaction.direction === "credit";

                  return (
                    <tr
                      key={transaction.id}
                      className={onOpen ? "clickable" : ""}
                      // The whole row opens the detail, but clicks inside the
                      // category dropdown must not — changing a category and
                      // opening a drawer are different intents.
                      onClick={(event) => {
                        if (event.target.closest("select")) return;
                        onOpen?.(transaction.id);
                      }}
                    >
                      <td className="date" data-label="Date">
                        {formatDate(transaction.date)}
                      </td>

                      <td
                        className="desc"
                        data-label="Merchant"
                        title={transaction.description}
                      >
                        <strong>{transaction.merchant}</strong>
                        <div className="tile-meta">
                          {shortenDescription(transaction.description, 42)}
                        </div>
                      </td>

                      <td data-label="Category">
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "var(--sp-2)",
                          }}
                        >
                          <span aria-hidden="true">
                            {categoryEmoji(transaction.category)}
                          </span>
                          <label
                            className="visually-hidden"
                            htmlFor={`category-${transaction.id}`}
                          >
                            Category for {transaction.description}
                          </label>
                          <select
                            id={`category-${transaction.id}`}
                            className="select select-sm"
                            style={{ width: "auto", minWidth: 132 }}
                            value={transaction.category}
                            disabled={saving}
                            onChange={(event) =>
                              onChangeCategory(transaction.id, event.target.value)
                            }
                          >
                            {/* Every category, including ones nothing uses
                                yet — otherwise a row could never be moved
                                into an empty one. */}
                            {categories.map((entry) => (
                              <option key={entry.category} value={entry.category}>
                                {formatCategory(entry.category)}
                              </option>
                            ))}
                          </select>
                          {saving && <span className="btn-spinner" />}
                        </div>
                      </td>

                      <td data-label="Labelled by">
                        <SourceBadge
                          source={transaction.category_source}
                          confidence={transaction.confidence}
                        />
                      </td>

                      <td className="num right" data-label="Amount">
                        <span className={credit ? "amount-in" : "amount-out"}>
                          {credit ? "+" : "−"}
                          {formatMoneyExact(transaction.amount)}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="pagination">
            <span>
              Showing {showingFrom.toLocaleString("en-IN")}–
              {showingTo.toLocaleString("en-IN")} of{" "}
              {total.toLocaleString("en-IN")}
            </span>
            <div className="pagination-buttons">
              <Button
                size="sm"
                disabled={offset === 0}
                onClick={() => onOffsetChange(Math.max(0, offset - PAGE_SIZE))}
              >
                Previous
              </Button>
              <Button
                size="sm"
                disabled={showingTo >= total}
                onClick={() => onOffsetChange(offset + PAGE_SIZE)}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}
    </Card>
  );
}

export { PAGE_SIZE };
