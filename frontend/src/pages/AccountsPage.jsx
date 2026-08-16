import { useState } from "react";

import * as api from "../api.js";
import Card, { CardBody, CardFoot, CardHead } from "../components/ui/Card.jsx";
import Button from "../components/ui/Button.jsx";
import ConfirmDialog from "../components/ui/Modal.jsx";
import { EmptyState, ErrorState, TableSkeleton } from "../components/ui/Feedback.jsx";
import { IconDatabase, IconTrash, IconWallet } from "../icons.jsx";
import useResource from "../useResource.js";

/**
 * The bank accounts statements are uploaded for.
 *
 * Without this, two banks' statements merge into one undifferentiated pile:
 * a salary credit from HDFC and a card payment from SBI land in the same
 * totals with nothing saying they came from different places.
 *
 * Two decisions worth knowing:
 *   - Deleting an account keeps its transactions. Removing a label should not
 *     delete a year of records, and a mis-click while renaming should not be
 *     unrecoverable.
 *   - Only the last four digits of a number are ever stored. A full account
 *     number has no use anywhere in this app.
 */
export default function AccountsPage({
  sources,
  dataVersion,
  onError,
  onSuccess,
  onChanged,
}) {
  const accounts = useResource(() => api.getAccounts(), [dataVersion]);

  const [name, setName] = useState("");
  const [bank, setBank] = useState("");
  const [last4, setLast4] = useState("");
  const [kind, setKind] = useState("savings");
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(null);
  const [assigning, setAssigning] = useState(null);

  async function addAccount(event) {
    event.preventDefault();
    setBusy(true);
    try {
      const account = await api.createAccount({ name, bank, last4, kind });
      onSuccess(`Added ${account.name}.`);
      setName("");
      setBank("");
      setLast4("");
      accounts.reload();
    } catch (error) {
      onError(error);
    } finally {
      setBusy(false);
    }
  }

  async function removeAccount(account) {
    setConfirming(null);
    try {
      const result = await api.deleteAccount(account.id);
      onSuccess(
        `${result.name} deleted. Its ${result.transactions_unassigned.toLocaleString("en-IN")} ` +
          `transactions are still here, now unassigned.`
      );
      accounts.reload();
      await onChanged();
    } catch (error) {
      onError(error);
    }
  }

  async function assign(uploadId, accountId) {
    setAssigning(uploadId);
    try {
      const result = await api.assignStatement({
        uploadId,
        accountId: accountId === "" ? null : Number(accountId),
      });
      onSuccess(`${result.moved.toLocaleString("en-IN")} transactions reassigned.`);
      accounts.reload();
      await onChanged();
    } catch (error) {
      onError(error);
    } finally {
      setAssigning(null);
    }
  }

  if (accounts.loading && !accounts.data) return <TableSkeleton rows={4} />;

  if (accounts.error) {
    return (
      <Card>
        <ErrorState
          title="We couldn't load your accounts"
          error={accounts.error}
          onRetry={accounts.reload}
        />
      </Card>
    );
  }

  const list = accounts.data || [];
  const real = list.filter((entry) => entry.id !== null);

  return (
    <div className="stack">
      <Card>
        <CardHead title="Add an account" description="One per bank account you upload statements for" bordered />
        <CardBody>
          <form className="account-form" onSubmit={addAccount}>
            <div className="field">
              <label htmlFor="acc-name">Name</label>
              <input
                id="acc-name"
                className="input"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="HDFC Salary"
                maxLength={60}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="acc-bank">Bank</label>
              <input
                id="acc-bank"
                className="input"
                value={bank}
                onChange={(event) => setBank(event.target.value)}
                placeholder="HDFC Bank"
                maxLength={60}
              />
            </div>
            <div className="field">
              <label htmlFor="acc-last4">Last 4 digits</label>
              <input
                id="acc-last4"
                className="input"
                value={last4}
                onChange={(event) => setLast4(event.target.value)}
                placeholder="8891"
                maxLength={4}
                inputMode="numeric"
              />
              <span className="hint">Optional. Only these four are stored.</span>
            </div>
            <div className="field">
              <label htmlFor="acc-kind">Type</label>
              <select
                id="acc-kind"
                className="select"
                value={kind}
                onChange={(event) => setKind(event.target.value)}
              >
                <option value="savings">Savings</option>
                <option value="current">Current</option>
                <option value="credit card">Credit card</option>
              </select>
            </div>
            <Button type="submit" variant="primary" loading={busy} disabled={name.trim().length < 2}>
              Add account
            </Button>
          </form>
        </CardBody>
        <CardFoot>
          Never enter a full account or card number. Only the last four digits
          are kept, and nothing in this app needs more than that.
        </CardFoot>
      </Card>

      <Card>
        <CardHead
          title="Your accounts"
          description={real.length ? `${real.length} account${real.length === 1 ? "" : "s"}` : "None yet"}
          bordered
        />
        {list.length === 0 ? (
          <CardBody>
            <EmptyState
              icon={IconWallet}
              title="No accounts yet"
              description="Add one above, then assign your statements to it below. Once you have two, every page can be filtered to one bank."
            />
          </CardBody>
        ) : (
          <div className="table-wrap">
            <table className="cards-on-mobile">
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Bank</th>
                  <th>Type</th>
                  <th className="right">Transactions</th>
                  <th className="right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {list.map((account) => (
                  <tr key={account.id ?? "unassigned"}>
                    <td data-label="Account">
                      <span className="merchant-name">{account.name}</span>
                      {account.last4 && <span className="muted"> ••••{account.last4}</span>}
                    </td>
                    <td data-label="Bank">{account.bank || "—"}</td>
                    <td data-label="Type">{account.kind}</td>
                    <td className="num right" data-label="Transactions">
                      {account.transaction_count.toLocaleString("en-IN")}
                    </td>
                    <td className="right" data-label="Actions">
                      {account.id === null ? (
                        <span className="muted">Statements with no account</span>
                      ) : (
                        <Button
                          size="sm"
                          variant="ghost"
                          icon={IconTrash}
                          onClick={() => setConfirming(account)}
                          aria-label={`Delete ${account.name}`}
                        />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card>
        <CardHead
          title="Which statement belongs where"
          description="Assign uploaded files to an account"
          bordered
        />
        {sources.length === 0 ? (
          <CardBody>
            <EmptyState
              icon={IconDatabase}
              title="No statements uploaded"
              description="Upload a statement first, then come back to assign it."
            />
          </CardBody>
        ) : (
          <div className="table-wrap">
            <table className="cards-on-mobile">
              <thead>
                <tr>
                  <th>File</th>
                  <th className="right">Transactions</th>
                  <th>Account</th>
                </tr>
              </thead>
              <tbody>
                {sources.map((entry) => (
                  <tr key={entry.upload_id}>
                    <td data-label="File">
                      <span className="merchant-name">{entry.filename}</span>
                    </td>
                    <td className="num right" data-label="Transactions">
                      {entry.count.toLocaleString("en-IN")}
                    </td>
                    <td data-label="Account">
                      <select
                        className="select select-sm"
                        defaultValue=""
                        disabled={assigning === entry.upload_id || real.length === 0}
                        onChange={(event) => assign(entry.upload_id, event.target.value)}
                        aria-label={`Account for ${entry.filename}`}
                      >
                        <option value="">Unassigned</option>
                        {real.map((account) => (
                          <option key={account.id} value={account.id}>
                            {account.name}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <CardFoot>
          Assigning a statement moves every transaction that came from it, so
          the account filter and the file filter can never disagree.
        </CardFoot>
      </Card>

      <ConfirmDialog
        open={Boolean(confirming)}
        title={`Delete ${confirming?.name}?`}
        confirmLabel="Delete account"
        onCancel={() => setConfirming(null)}
        onConfirm={() => removeAccount(confirming)}
      >
        <p>
          Its {confirming?.transaction_count.toLocaleString("en-IN")} transactions
          stay exactly where they are — they simply stop being assigned to an
          account.
        </p>
        <p style={{ marginTop: "var(--sp-3)" }}>
          Nothing is removed from your totals, charts or history.
        </p>
      </ConfirmDialog>
    </div>
  );
}
