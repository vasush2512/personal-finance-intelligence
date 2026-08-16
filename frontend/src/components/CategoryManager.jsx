import { useState } from "react";

import * as api from "../api.js";
import Card, { CardBody, CardFoot, CardHead } from "./ui/Card.jsx";
import Button from "./ui/Button.jsx";
import ConfirmDialog from "./ui/Modal.jsx";
import { EmptyState, ErrorState, TableSkeleton } from "./ui/Feedback.jsx";
import { IconTags, IconTrash } from "../icons.jsx";
import { formatCategory } from "../format.js";
import useResource from "../useResource.js";

/**
 * Categories the user defined, and what happens when they change them.
 *
 * Lives on the existing Categories page rather than on a new one: a category
 * is a category, and splitting "the twelve that came with the app" from "the
 * ones you made" across two screens would be an implementation detail leaking
 * into the navigation.
 *
 * The delete flow is the interesting part. A category in use cannot simply be
 * removed — the backend refuses with a count, and this offers the two things
 * that are actually safe: archive it, or move its transactions somewhere else
 * first. Neither one loses history.
 */
export default function CategoryManager({
  choices,
  dataVersion,
  onError,
  onSuccess,
  onChanged,
}) {
  const mine = useResource(
    () => api.getUserCategories({ include_archived: true }),
    [dataVersion]
  );

  const [label, setLabel] = useState("");
  const [emoji, setEmoji] = useState("");
  const [kind, setKind] = useState("expense");
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState(null);
  const [moveTo, setMoveTo] = useState("other");

  async function create(event) {
    event.preventDefault();
    setBusy(true);
    try {
      const created = await api.createUserCategory({ label, emoji, kind });
      onSuccess(`Added ${created.label}.`);
      setLabel("");
      setEmoji("");
      mine.reload();
      await onChanged();
    } catch (error) {
      onError(error);
    } finally {
      setBusy(false);
    }
  }

  async function rename(category, nextLabel) {
    if (!nextLabel || nextLabel === category.label) return;
    try {
      await api.updateUserCategory(category.id, { label: nextLabel });
      // Renaming moves nothing: the key a transaction stores never changes.
      onSuccess(`Renamed to ${nextLabel}. No transaction moved.`);
      mine.reload();
      await onChanged();
    } catch (error) {
      onError(error);
    }
  }

  async function toggleArchive(category) {
    try {
      await api.updateUserCategory(category.id, { archived: !category.archived });
      onSuccess(
        category.archived
          ? `${category.label} is available again.`
          : `${category.label} archived — it stays on transactions already using it.`
      );
      mine.reload();
      await onChanged();
    } catch (error) {
      onError(error);
    }
  }

  async function remove(category, destination) {
    setDeleting(null);
    try {
      const result = await api.deleteUserCategory(category.id, destination);
      onSuccess(
        result.moved
          ? `${result.label} deleted. ${result.moved.toLocaleString("en-IN")} transactions moved to ${formatCategory(destination)}.`
          : `${result.label} deleted.`
      );
      mine.reload();
      await onChanged();
    } catch (error) {
      onError(error);
    }
  }

  if (mine.loading && !mine.data) return <TableSkeleton rows={3} />;

  if (mine.error) {
    return (
      <Card>
        <ErrorState
          title="We couldn't load your categories"
          error={mine.error}
          onRetry={mine.reload}
        />
      </Card>
    );
  }

  const list = mine.data || [];
  const counts = Object.fromEntries(
    (choices || []).map((entry) => [entry.category, entry.count])
  );
  const destinations = (choices || []).filter(
    (entry) => !entry.archived && entry.category !== deleting?.key
  );

  return (
    <div className="stack">
      <Card>
        <CardHead
          title="Your own categories"
          description="Alongside the built-in ones, not instead of them"
          bordered
        />
        <CardBody>
          <form className="rule-form" onSubmit={create}>
            <div className="field">
              <label htmlFor="cat-label">Name</label>
              <input
                id="cat-label"
                className="input"
                value={label}
                onChange={(event) => setLabel(event.target.value)}
                placeholder="Gym"
                maxLength={40}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="cat-emoji">Icon</label>
              <input
                id="cat-emoji"
                className="input"
                value={emoji}
                onChange={(event) => setEmoji(event.target.value)}
                placeholder="🏋️"
                maxLength={4}
              />
              <span className="hint">An emoji, optional.</span>
            </div>
            <div className="field">
              <label htmlFor="cat-kind">Used for</label>
              <select
                id="cat-kind"
                className="select"
                value={kind}
                onChange={(event) => setKind(event.target.value)}
              >
                <option value="expense">Expenses</option>
                <option value="income">Income</option>
              </select>
            </div>
            <Button
              type="submit"
              variant="primary"
              loading={busy}
              disabled={label.trim().length < 2}
            >
              Add category
            </Button>
          </form>
        </CardBody>
        <CardFoot>
          Your categories are yours alone — nobody else's account can see or use
          them. They work everywhere a built-in category does.
        </CardFoot>
      </Card>

      <Card>
        <CardHead
          title={list.length ? `${list.length} custom` : "None yet"}
          description="Rename freely — the transactions never move"
          bordered
        />

        {list.length === 0 ? (
          <CardBody>
            <EmptyState
              icon={IconTags}
              title="No custom categories"
              description="The twelve built-in ones cover most spending. Add your own for anything they miss — Gym, Pets, College, a side project."
            />
          </CardBody>
        ) : (
          <div className="table-wrap">
            <table className="cards-on-mobile">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Used for</th>
                  <th className="right">Transactions</th>
                  <th>Status</th>
                  <th className="right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {list.map((category) => (
                  <tr key={category.id}>
                    <td data-label="Name">
                      <span className="category-name">
                        {category.emoji && (
                          <span aria-hidden="true">{category.emoji} </span>
                        )}
                        <input
                          className="inline-edit"
                          defaultValue={category.label}
                          maxLength={40}
                          aria-label={`Rename ${category.label}`}
                          onBlur={(event) =>
                            rename(category, event.target.value.trim())
                          }
                          onKeyDown={(event) =>
                            event.key === "Enter" && event.target.blur()
                          }
                        />
                      </span>
                    </td>
                    <td data-label="Used for">
                      {category.kind === "income" ? "Income" : "Expenses"}
                    </td>
                    <td className="num right" data-label="Transactions">
                      {(counts[category.key] || 0).toLocaleString("en-IN")}
                    </td>
                    <td data-label="Status">
                      <button
                        type="button"
                        className={`badge badge-${category.archived ? "neutral" : "success"} chip-button`}
                        onClick={() => toggleArchive(category)}
                        title={
                          category.archived
                            ? "Offer this category again"
                            : "Stop offering it on forms; existing transactions keep it"
                        }
                      >
                        {category.archived ? "Archived" : "Active"}
                      </button>
                    </td>
                    <td className="right" data-label="Actions">
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={IconTrash}
                        onClick={() => {
                          setMoveTo("other");
                          setDeleting(category);
                        }}
                        aria-label={`Delete ${category.label}`}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <CardFoot>
          Renaming changes only the label. Every transaction keeps pointing at
          the same category, because what they store is a stable key rather than
          the name you see.
        </CardFoot>
      </Card>

      <ConfirmDialog
        open={Boolean(deleting)}
        title={`Delete ${deleting?.label}?`}
        confirmLabel={
          (counts[deleting?.key] || 0) > 0 ? "Move and delete" : "Delete"
        }
        onCancel={() => setDeleting(null)}
        onConfirm={() =>
          remove(deleting, (counts[deleting?.key] || 0) > 0 ? moveTo : undefined)
        }
      >
        {(counts[deleting?.key] || 0) > 0 ? (
          <>
            <p>
              <strong>
                {(counts[deleting?.key] || 0).toLocaleString("en-IN")} transactions
              </strong>{" "}
              use this category. Deleting it would leave them pointing at
              something that no longer exists, so they have to go somewhere.
            </p>
            <div className="field" style={{ marginTop: "var(--sp-4)" }}>
              <label htmlFor="move-to">Move them to</label>
              <select
                id="move-to"
                className="select"
                value={moveTo}
                onChange={(event) => setMoveTo(event.target.value)}
              >
                {destinations.map((entry) => (
                  <option key={entry.category} value={entry.category}>
                    {entry.label}
                  </option>
                ))}
              </select>
            </div>
            <p className="note" style={{ marginTop: "var(--sp-3)" }}>
              Prefer to keep them where they are? Cancel and archive it instead —
              the category stops being offered but stays on every transaction
              already using it.
            </p>
          </>
        ) : (
          <p>Nothing is using this category, so nothing will move.</p>
        )}
      </ConfirmDialog>
    </div>
  );
}
