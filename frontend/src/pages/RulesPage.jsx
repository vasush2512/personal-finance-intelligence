import { useState } from "react";

import * as api from "../api.js";
import Card, { CardBody, CardFoot, CardHead } from "../components/ui/Card.jsx";
import Button from "../components/ui/Button.jsx";
import { EmptyState, ErrorState, TableSkeleton } from "../components/ui/Feedback.jsx";
import { IconCheck, IconTags, IconTrash, IconX } from "../icons.jsx";
import { formatCategory, formatDate, formatMoney, shortenDescription } from "../format.js";
import useResource from "../useResource.js";

/**
 * Rules the user writes, matching a keyword to a category.
 *
 * This exists because the built-in rules leave a lot uncategorised on real
 * data — nearly half, in the case that prompted it — and the person using the
 * app cannot edit the file those rules live in.
 *
 * The design decision worth knowing: you preview before you apply. A rule can
 * touch a hundred thousand rows, and finding out what it did afterwards is not
 * a reasonable way to learn. So the count and a sample come first, then the
 * button that actually writes.
 */
export default function RulesPage({
  categories,
  dataVersion,
  onError,
  onSuccess,
  onChanged,
}) {
  const rules = useResource(() => api.getRules(), [dataVersion]);

  const [keyword, setKeyword] = useState("");
  const [category, setCategory] = useState("groceries");
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [applyingId, setApplyingId] = useState(null);

  async function runPreview() {
    if (keyword.trim().length < 2) return;
    setBusy(true);
    try {
      setPreview(await api.previewRule(keyword.trim()));
    } catch (error) {
      onError(error);
      setPreview(null);
    } finally {
      setBusy(false);
    }
  }

  async function saveRule() {
    setBusy(true);
    try {
      const rule = await api.createRule({ keyword: keyword.trim(), category });
      // Saving and applying are separate on purpose: a new rule affects future
      // imports immediately, but rewriting existing rows is a bigger step and
      // stays a deliberate one.
      onSuccess(
        `Rule saved. New imports containing "${rule.keyword}" will be ` +
          `${formatCategory(rule.category)}. Use Apply to change existing rows.`
      );
      setKeyword("");
      setPreview(null);
      rules.reload();
    } catch (error) {
      onError(error);
    } finally {
      setBusy(false);
    }
  }

  async function applyExisting(rule) {
    setApplyingId(rule.id);
    try {
      const result = await api.applyRule(rule.id);
      onSuccess(
        result.rows_changed
          ? `${result.rows_changed.toLocaleString("en-IN")} transactions moved to ${formatCategory(rule.category)}.`
          : "No uncategorised transactions matched that rule."
      );
      if (result.rows_changed) await onChanged();
    } catch (error) {
      onError(error);
    } finally {
      setApplyingId(null);
    }
  }

  async function removeRule(rule) {
    try {
      await api.deleteRule(rule.id);
      onSuccess(
        `Rule for "${rule.keyword}" deleted. Transactions it already ` +
          `categorised keep their category.`
      );
      rules.reload();
    } catch (error) {
      onError(error);
    }
  }

  async function toggle(rule) {
    try {
      await api.updateRule(rule.id, { active: !rule.active });
      rules.reload();
    } catch (error) {
      onError(error);
    }
  }

  if (rules.loading && !rules.data) return <TableSkeleton rows={4} />;

  if (rules.error) {
    return (
      <Card>
        <ErrorState title="We couldn't load your rules" error={rules.error} onRetry={rules.reload} />
      </Card>
    );
  }

  const list = rules.data || [];

  return (
    <div className="stack">
      <Card>
        <CardHead
          title="Add a rule"
          description="If a transaction's description contains this word, use this category"
          bordered
        />
        <CardBody>
          <div className="rule-form">
            <div className="field">
              <label htmlFor="rule-keyword">Description contains</label>
              <input
                id="rule-keyword"
                className="input"
                value={keyword}
                onChange={(event) => {
                  setKeyword(event.target.value);
                  setPreview(null);
                }}
                placeholder="BLINKIT"
                maxLength={120}
              />
              <span className="hint">
                Not case sensitive. Matched anywhere in the description.
              </span>
            </div>

            <div className="field">
              <label htmlFor="rule-category">Category</label>
              <select
                id="rule-category"
                className="select"
                value={category}
                onChange={(event) => setCategory(event.target.value)}
              >
                {categories.map((entry) => (
                  <option key={entry.category} value={entry.category}>
                    {formatCategory(entry.category)}
                  </option>
                ))}
              </select>
            </div>

            <Button
              variant="secondary"
              onClick={runPreview}
              loading={busy && !preview}
              disabled={keyword.trim().length < 2}
            >
              Preview
            </Button>
          </div>

          {preview && (
            <div className="rule-preview">
              <p className="note">
                <strong>{preview.matches.toLocaleString("en-IN")}</strong>{" "}
                uncategorised transaction
                {preview.matches === 1 ? "" : "s"} contain "{preview.keyword}".
                {preview.matches === 0 &&
                  " The rule will still apply to future imports."}
              </p>

              {preview.samples.length > 0 && (
                <div className="table-wrap">
                  <table className="cards-on-mobile">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Description</th>
                        <th className="right">Amount</th>
                        <th>Now</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.samples.map((row) => (
                        <tr key={row.id}>
                          <td className="num" data-label="Date">{formatDate(row.date)}</td>
                          <td className="desc" data-label="Description">
                            {shortenDescription(row.description, 46)}
                          </td>
                          <td className="num right" data-label="Amount">
                            {formatMoney(row.amount)}
                          </td>
                          <td data-label="Now">
                            <span className="muted">
                              {formatCategory(row.current_category)}
                            </span>{" "}
                            → <strong>{formatCategory(category)}</strong>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <div className="pair-actions" style={{ borderTop: "none" }}>
                <Button variant="primary" icon={IconCheck} loading={busy} onClick={saveRule}>
                  Save this rule
                </Button>
              </div>
            </div>
          )}
        </CardBody>
        <CardFoot>
          Your rules run before the built-in ones and win over them. They never
          change a category you set by hand.
        </CardFoot>
      </Card>

      <Card>
        <CardHead
          title="Your rules"
          description={
            list.length
              ? `${list.length} rule${list.length === 1 ? "" : "s"}, applied top to bottom`
              : "None yet"
          }
          bordered
        />
        {list.length === 0 ? (
          <CardBody>
            <EmptyState
              icon={IconTags}
              title="No rules yet"
              description="Add one above. Rules are the fastest way to clear out transactions nothing could categorise — one rule can fix thousands of rows at once."
            />
          </CardBody>
        ) : (
          <div className="table-wrap">
            <table className="cards-on-mobile">
              <thead>
                <tr>
                  <th>Description contains</th>
                  <th>Category</th>
                  <th>Status</th>
                  <th className="right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {list.map((rule) => (
                  <tr key={rule.id}>
                    <td data-label="Contains">
                      <span className="merchant-name">{rule.keyword}</span>
                    </td>
                    <td data-label="Category">{formatCategory(rule.category)}</td>
                    <td data-label="Status">
                      <button
                        type="button"
                        className={`badge badge-${rule.active ? "success" : "neutral"} chip-button`}
                        onClick={() => toggle(rule)}
                        title={rule.active ? "Turn this rule off" : "Turn this rule on"}
                      >
                        {rule.active ? "Active" : "Off"}
                      </button>
                    </td>
                    <td className="right" data-label="Actions">
                      <span className="rule-actions">
                        <Button
                          size="sm"
                          variant="secondary"
                          loading={applyingId === rule.id}
                          disabled={applyingId !== null || !rule.active}
                          onClick={() => applyExisting(rule)}
                        >
                          Apply to existing
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          icon={IconTrash}
                          onClick={() => removeRule(rule)}
                          aria-label={`Delete rule for ${rule.keyword}`}
                        />
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <CardFoot>
          "Apply to existing" only touches transactions nothing has categorised.
          Anything you corrected by hand is left alone, and deleting a rule does
          not undo categories it already applied.
        </CardFoot>
      </Card>
    </div>
  );
}
