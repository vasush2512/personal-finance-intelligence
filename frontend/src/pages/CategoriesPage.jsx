import CategoryManager from "../components/CategoryManager.jsx";
import Card, { CardHead, CardFoot } from "../components/ui/Card.jsx";
import Badge from "../components/ui/Badge.jsx";
import { categoryEmoji } from "../icons.jsx";
import { formatCategory, formatMoney, toNumber } from "../format.js";
import { navigate } from "../router.js";

/**
 * The category vocabulary, with how much sits in each.
 *
 * Read-only on purpose: categories are defined in the backend's constants.py
 * and there is no endpoint to add or rename one. Rendering an "Add category"
 * button that cannot work would be worse than not having it — so this page
 * shows what exists, how full each one is, and gets out of the way.
 *
 * Clicking a category jumps to the filtered transaction list, which is the
 * only action this data actually supports.
 */
export default function CategoriesPage({
  categories,
  summary,
  onSelectCategory,
  choices,
  dataVersion,
  onError,
  onSuccess,
  onChanged,
}) {
  // /api/categories gives the vocabulary and row counts; /api/summary gives
  // spending per category. Joined here rather than asking the backend for a
  // combined shape that no other screen needs.
  const spendByCategory = Object.fromEntries(
    summary.by_category.map((row) => [row.category, toNumber(row.total)])
  );

  const used = categories.filter((entry) => entry.count > 0);
  const unused = categories.filter((entry) => entry.count === 0);
  const largest = Math.max(...Object.values(spendByCategory), 0);

  function open(category) {
    onSelectCategory(category);
    navigate("/transactions");
  }

  return (
    <div className="stack">
      <div className="grid-3">
        {used.map((entry) => {
          const spent = spendByCategory[entry.category] || 0;

          return (
            <button
              key={entry.category}
              className="card category-tile"
              onClick={() => open(entry.category)}
              aria-label={`View ${formatCategory(entry.category)} transactions`}
            >
              <span
                className="tile-icon"
                style={{ background: "var(--surface-hover)" }}
                aria-hidden="true"
              >
                {categoryEmoji(entry.category)}
              </span>

              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="tile-name">{formatCategory(entry.category)}</div>
                <div className="tile-meta">
                  {entry.count.toLocaleString("en-IN")} transaction
                  {entry.count === 1 ? "" : "s"}
                  {spent > 0 && ` · ${formatMoney(spent)}`}
                </div>

                {spent > 0 && (
                  <div className="bar-track">
                    <div
                      className="bar-fill"
                      style={{ width: `${largest ? (spent / largest) * 100 : 0}%` }}
                    />
                  </div>
                )}
              </div>
            </button>
          );
        })}
      </div>

      {unused.length > 0 && (
        <Card>
          <CardHead
            title="Not in use yet"
            description="Valid categories that no transaction currently carries. You can still move a row into one of these from the transactions table."
          />
          <div
            className="card-body"
            style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-2)" }}
          >
            {unused.map((entry) => (
              <Badge key={entry.category} tone="neutral">
                <span aria-hidden="true">{categoryEmoji(entry.category)}</span>
                {formatCategory(entry.category)}
              </Badge>
            ))}
          </div>
        </Card>
      )}

      <Card>
        <CardHead title="How categories are assigned" />
        <div className="card-body">
          <p className="prose">
            Every imported row is matched against about sixty keyword rules
            first — Swiggy is food, Blinkit is groceries. Whatever no rule
            recognises is passed to a classifier trained on the rules' own
            output, which generalises to merchants no rule names. If it is less
            than 55% sure, the row stays <strong>other</strong> rather than
            guessing.
          </p>
          <p className="prose">
            Correcting a category from the transactions table marks that row as
            yours. Nothing overwrites it afterwards, and it becomes training
            data the next time the model is fitted.
          </p>
        </div>
        <CardFoot>
          Category names are defined once, in the backend, and read from{" "}
          <code>GET /api/categories</code> — so this list can never drift out of
          step with what the server will accept.
        </CardFoot>
      </Card>

      {/* The user's own categories, on the same page as the built-in ones:
          a category is a category, and splitting them across two screens
          would put an implementation detail into the navigation. */}
      {onChanged && (
        <CategoryManager
          choices={choices}
          dataVersion={dataVersion}
          onError={onError}
          onSuccess={onSuccess}
          onChanged={onChanged}
        />
      )}
    </div>
  );
}
