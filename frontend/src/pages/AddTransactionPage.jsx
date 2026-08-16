import { useEffect, useRef, useState } from "react";

import * as api from "../api.js";
import Card, { CardBody, CardFoot, CardHead } from "../components/ui/Card.jsx";
import Button from "../components/ui/Button.jsx";
import { IconArrowRight, IconCheck } from "../icons.jsx";
import { navigate } from "../router.js";

/**
 * Recording one transaction, on a page of its own.
 *
 * This replaced a right-hand drawer that showed every field at once. Nine
 * inputs arriving together made a ₹40 chai feel like paperwork, which is the
 * opposite of what a manual-entry feature is for.
 *
 * So the shape is: four fields to record something, and everything else behind
 * "More details". The advanced fields are all still here and all still
 * optional — nothing was removed to make the form look shorter.
 *
 * On the suggestion: the backend matches keyword rules, which either match or
 * do not. There is no probability behind them, so none is shown. A "93%
 * confident" badge would be a number this app cannot compute, and inventing
 * one to make the feature look cleverer is the exact thing the rest of the
 * project refuses to do.
 */
export default function AddTransactionPage({
  categories,
  accounts,
  onSaved,
  onError,
}) {
  const [direction, setDirection] = useState("expense");
  const [amount, setAmount] = useState("");
  const [merchant, setMerchant] = useState("");
  const [category, setCategory] = useState("");
  const [date, setDate] = useState(today());

  const [showMore, setShowMore] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState("");
  const [accountId, setAccountId] = useState("");
  const [tags, setTags] = useState("");
  const [notes, setNotes] = useState("");

  const [suggestion, setSuggestion] = useState(null);
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);
  const amountRef = useRef(null);

  // The amount is the one field always filled, so the cursor starts there.
  useEffect(() => {
    const timer = setTimeout(() => amountRef.current?.focus(), 60);
    return () => clearTimeout(timer);
  }, []);

  /**
   * Ask the existing rules what this merchant looks like, once typing pauses.
   *
   * Debounced for the same reason the transaction search is: a request per
   * keystroke is six requests to answer one question. Skipped entirely once a
   * category has been chosen — at that point the answer is settled.
   */
  useEffect(() => {
    if (category || merchant.trim().length < 3) {
      setSuggestion(null);
      return undefined;
    }
    const timer = setTimeout(() => {
      api
        .suggestCategory(merchant.trim())
        .then((result) => setSuggestion(result.category ? result : null))
        .catch(() => setSuggestion(null));
    }, 350);
    return () => clearTimeout(timer);
  }, [merchant, category]);

  /** Plain sentences, checked before anything is sent. */
  function validate() {
    const found = {};
    const value = amount.trim();

    if (!value) {
      found.amount = "Enter an amount.";
    } else if (Number.isNaN(Number(value.replace(/,/g, "")))) {
      found.amount = "Enter the amount as a number, like 250 or 250.50.";
    } else if (Number(value.replace(/,/g, "")) <= 0) {
      found.amount = "The amount has to be more than zero.";
    }

    if (!date) {
      found.date = "Pick a date.";
    } else if (date > today()) {
      found.date = "That date is in the future.";
    }

    setErrors(found);
    return Object.keys(found).length === 0;
  }

  async function save(event) {
    event.preventDefault();
    if (saving || !validate()) return;

    setSaving(true);
    try {
      const created = await api.addManual({
        amount: amount.trim(),
        date,
        direction,
        // A suggestion on screen when you press Save is one you accepted.
        // What is never sent is a guess you were not shown.
        category: category || suggestion?.category || null,
        merchant: merchant.trim(),
        payment_method: paymentMethod,
        notes: notes.trim(),
        account_id: accountId ? Number(accountId) : null,
        tags: tags.split(",").map((tag) => tag.trim()).filter(Boolean),
      });

      await onSaved(created);
      navigate("/personal");
    } catch (error) {
      // The backend validates too, and its refusals are already written to be
      // read. Shown through the app's usual toast rather than as raw JSON.
      onError(error);
    } finally {
      setSaving(false);
    }
  }

  const expense = direction === "expense";
  const usable = (categories || []).filter(
    (entry) => !entry.archived && (expense ? entry.kind !== "income" : true)
  );
  const realAccounts = (accounts || []).filter((entry) => entry.id !== null);

  return (
    <div className="entry-page">
      <button type="button" className="back-link" onClick={() => navigate("/personal")}>
        <span aria-hidden="true">←</span> Personal Expenses
      </button>

      <Card className="entry-card">
        <CardHead
          title="Add transaction"
          description="Record an expense or income by hand"
          bordered
        />

        <form onSubmit={save} noValidate>
          <CardBody className="entry-body">
            <div className="segmented entry-type" role="radiogroup" aria-label="Type">
              <button
                type="button"
                role="radio"
                aria-checked={expense}
                onClick={() => setDirection("expense")}
              >
                Expense
              </button>
              <button
                type="button"
                role="radio"
                aria-checked={!expense}
                onClick={() => setDirection("income")}
              >
                Income
              </button>
            </div>

            <div className="field">
              <label htmlFor="amount">Amount</label>
              <div className={`amount-input entry-amount ${errors.amount ? "invalid" : ""}`}>
                <span aria-hidden="true">₹</span>
                <input
                  id="amount"
                  ref={amountRef}
                  className="input"
                  value={amount}
                  onChange={(event) => setAmount(event.target.value)}
                  placeholder="250"
                  inputMode="decimal"
                  aria-invalid={Boolean(errors.amount)}
                  aria-describedby={errors.amount ? "amount-error" : undefined}
                />
              </div>
              {errors.amount ? (
                <span className="field-error" id="amount-error">
                  {errors.amount}
                </span>
              ) : (
                <span className="hint">
                  Always positive — money in or out is the choice above.
                </span>
              )}
            </div>

            <div className="field">
              <label htmlFor="merchant">
                {expense ? "What did you spend on?" : "Where did it come from?"}
              </label>
              <input
                id="merchant"
                className="input"
                value={merchant}
                onChange={(event) => setMerchant(event.target.value)}
                placeholder={expense ? "Chai Point" : "Employer"}
                maxLength={80}
              />
            </div>

            <div className="field">
              <label htmlFor="category">Category</label>
              <select
                id="category"
                className="select"
                value={category}
                onChange={(event) => setCategory(event.target.value)}
              >
                <option value="">Not sure yet</option>
                {usable.map((entry) => (
                  <option key={entry.category} value={entry.category}>
                    {entry.emoji ? `${entry.emoji} ` : ""}
                    {entry.label}
                    {entry.custom ? " (yours)" : ""}
                  </option>
                ))}
              </select>

              {suggestion && !category && (
                <div className="suggestion">
                  <span>
                    Suggested: <strong>{suggestion.label}</strong>
                    <span className="muted"> — matched a keyword rule</span>
                  </span>
                  <Button
                    size="sm"
                    variant="secondary"
                    icon={IconCheck}
                    onClick={() => setCategory(suggestion.category)}
                  >
                    Use it
                  </Button>
                </div>
              )}
            </div>

            <div className="field">
              <label htmlFor="date">Date</label>
              <input
                id="date"
                className="input"
                type="date"
                value={date}
                max={today()}
                onChange={(event) => setDate(event.target.value)}
                aria-invalid={Boolean(errors.date)}
              />
              {errors.date && <span className="field-error">{errors.date}</span>}
            </div>

            {/* Everything below is optional and stays out of the way until
                asked for. None of it was removed — it moved. */}
            <button
              type="button"
              className="more-toggle"
              onClick={() => setShowMore((open) => !open)}
              aria-expanded={showMore}
            >
              <span className={`more-caret ${showMore ? "open" : ""}`} aria-hidden="true">
                <IconArrowRight size={13} />
              </span>
              {showMore ? "Fewer details" : "More details"}
            </button>

            {showMore && (
              <div className="entry-more">
                <div className="add-row">
                  <div className="field">
                    <label htmlFor="payment-method">Payment method</label>
                    <select
                      id="payment-method"
                      className="select"
                      value={paymentMethod}
                      onChange={(event) => setPaymentMethod(event.target.value)}
                    >
                      <option value="">Not recorded</option>
                      {PAYMENT_METHODS.map((method) => (
                        <option key={method} value={method}>
                          {method}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="field">
                    <label htmlFor="account">Account</label>
                    <select
                      id="account"
                      className="select"
                      value={accountId}
                      onChange={(event) => setAccountId(event.target.value)}
                      disabled={realAccounts.length === 0}
                    >
                      <option value="">
                        {realAccounts.length ? "Not assigned" : "No accounts yet"}
                      </option>
                      {realAccounts.map((entry) => (
                        <option key={entry.id} value={entry.id}>
                          {entry.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="field">
                  <label htmlFor="tags">Tags</label>
                  <input
                    id="tags"
                    className="input"
                    value={tags}
                    onChange={(event) => setTags(event.target.value)}
                    placeholder="delhi trip, friends"
                  />
                  <span className="hint">
                    Separated by commas. Tags never change a category or a total.
                  </span>
                </div>

                <div className="field">
                  <label htmlFor="notes">Notes</label>
                  <input
                    id="notes"
                    className="input"
                    value={notes}
                    onChange={(event) => setNotes(event.target.value)}
                    placeholder="Optional"
                    maxLength={500}
                  />
                </div>
              </div>
            )}
          </CardBody>

          <CardFoot>
            <div className="entry-actions">
              <Button
                type="button"
                variant="secondary"
                onClick={() => navigate("/personal")}
              >
                Cancel
              </Button>
              <Button type="submit" variant="primary" loading={saving}>
                Save transaction
              </Button>
            </div>
          </CardFoot>
        </form>
      </Card>
    </div>
  );
}

/** Kept in step with PAYMENT_METHODS in the backend constants. */
const PAYMENT_METHODS = [
  "Cash", "UPI", "Card", "Credit Card", "Debit Card", "Net banking",
  "NEFT", "IMPS", "Wallet", "Cheque", "Auto-debit", "Other",
];

function today() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}
