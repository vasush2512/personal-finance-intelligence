import { useState } from "react";

import * as api from "../api.js";
import { decodeSource } from "../components/Filters.jsx";
import Card, { CardBody, CardFoot, CardHead } from "../components/ui/Card.jsx";
import Button from "../components/ui/Button.jsx";
import { EmptyState, ErrorState, TableSkeleton } from "../components/ui/Feedback.jsx";
import { IconCheck, IconCheckCircle, IconCopy, IconX } from "../icons.jsx";
import {
  formatCategory,
  formatDate,
  formatMoneyExact,
  shortenDescription,
} from "../format.js";
import useResource from "../useResource.js";

/**
 * Pairs that may be one payment recorded twice, and the user's answer.
 *
 * Two rules shape this whole screen, and both come from the same fact — only
 * the person who made the payments knows whether there were two of them:
 *
 *   1. Nothing is deleted. Not automatically, not on confirmation. Confirming
 *      records what you decided and takes the pair out of the queue.
 *   2. Nothing here claims to be a duplicate. Every label says "possible", and
 *      the reasons that produced the score are shown next to it, so the score
 *      is checkable rather than something to take on faith.
 *
 * Exact duplicates never reach this page — the import fingerprint drops those
 * before they are stored. What is left are the near-misses: the same amount at
 * the same merchant a day or two apart, which is what a delayed card
 * settlement and a genuine double charge both look like.
 */
export default function DuplicatesPage({
  source,
  dataVersion,
  onError,
  onSuccess,
  onOpenTransaction,
}) {
  const pairs = useResource(
    () => api.getDuplicates(decodeSource(source)),
    [source, dataVersion]
  );

  // Which pair is mid-request, keyed the same way the backend identifies it.
  const [decidingKey, setDecidingKey] = useState(null);

  async function decide(pair, isDuplicate) {
    const key = pairKey(pair);
    setDecidingKey(key);
    try {
      await api.setDuplicateVerdict({
        firstId: pair.first.id,
        secondId: pair.second.id,
        isDuplicate,
      });

      // Drop it locally rather than re-fetching: the scan behind this list
      // takes seconds, and the answer to "is this pair still open" is already
      // known — it is not.
      pairs.setData(pairs.data.filter((entry) => pairKey(entry) !== key));

      onSuccess(
        isDuplicate
          ? "Marked as a duplicate. Both transactions are still in your data — nothing was deleted."
          : "Marked as two separate transactions. It won't be suggested again."
      );
    } catch (error) {
      onError(error);
    } finally {
      setDecidingKey(null);
    }
  }

  if (pairs.loading && !pairs.data) {
    return <TableSkeleton rows={4} />;
  }

  if (pairs.error) {
    return (
      <Card>
        <ErrorState
          title="We couldn't check for duplicates"
          error={pairs.error}
          onRetry={pairs.reload}
        />
      </Card>
    );
  }

  const open = pairs.data || [];

  if (open.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={IconCheckCircle}
          title="No possible duplicates found"
          description={
            "Nothing in your statements looks like the same payment recorded twice. " +
            "Identical rows are already removed when a file is imported, so this page " +
            "only looks for near-misses: the same amount at the same merchant within " +
            "three days."
          }
        />
      </Card>
    );
  }

  return (
    <div className="stack">
      <Card>
        <CardHead
          title={`${open.length} pair${open.length === 1 ? "" : "s"} to review`}
          description="Same amount, same merchant, a few days apart. Strongest match first."
          actions={
            <Button variant="secondary" onClick={pairs.reload} loading={pairs.loading}>
              Re-check
            </Button>
          }
        />
        <CardBody>
          <p className="note">
            Nothing on this page is deleted, before or after you answer. Marking
            a pair as a duplicate records your decision and removes it from this
            queue — both transactions stay in your data and in your totals.
          </p>
        </CardBody>
      </Card>

      {open.map((pair) => (
        <PairCard
          key={pairKey(pair)}
          pair={pair}
          busy={decidingKey === pairKey(pair)}
          disabled={decidingKey !== null}
          onDecide={decide}
          onOpenTransaction={onOpenTransaction}
        />
      ))}
    </div>
  );
}

/** Stable identity for a pair, matching how the backend orders the two ids. */
function pairKey(pair) {
  const low = Math.min(pair.first.id, pair.second.id);
  const high = Math.max(pair.first.id, pair.second.id);
  return `${low}-${high}`;
}

/**
 * The score is a similarity score, not a probability that this is a duplicate.
 * The tint reflects how much of the evidence lines up and nothing more.
 */
function scoreTone(score) {
  if (score >= 90) return "danger";
  if (score >= 80) return "warning";
  return "neutral";
}

function PairCard({ pair, busy, disabled, onDecide, onOpenTransaction }) {
  const gap =
    pair.days_apart === 0
      ? "Same day"
      : `${pair.days_apart} day${pair.days_apart === 1 ? "" : "s"} apart`;

  return (
    <Card className="pair">
      <CardHead
        title={
          <>
            {formatMoneyExact(pair.amount)} at {pair.merchant}
          </>
        }
        description={`${gap} · ${formatCategory(pair.first.category)}`}
        bordered
        actions={
          <span className={`badge badge-${scoreTone(pair.score)}`}>
            {pair.score}% similar
          </span>
        }
      />

      <CardBody>
        <div className="pair-sides">
          <PairSide
            side={pair.first}
            label="First recorded"
            onOpen={onOpenTransaction}
          />
          <PairSide
            side={pair.second}
            label="Then recorded"
            onOpen={onOpenTransaction}
          />
        </div>

        <div className="pair-reasons">
          <span className="pair-reasons-label">What matched</span>
          <div className="chips">
            {pair.reasons.map((reason) => (
              <span className="chip" key={reason}>
                {reason}
              </span>
            ))}
          </div>
        </div>

        <div className="pair-actions">
          <Button
            variant="primary"
            icon={IconCheck}
            loading={busy}
            disabled={disabled && !busy}
            onClick={() => onDecide(pair, true)}
          >
            Yes, it's a duplicate
          </Button>
          <Button
            variant="secondary"
            icon={IconX}
            disabled={disabled}
            onClick={() => onDecide(pair, false)}
          >
            No, two separate payments
          </Button>
        </div>
      </CardBody>

      <CardFoot>
        Two identical payments on one day are often genuinely two payments — a
        second round, a split bill, a retry that went through. Your answer is
        recorded either way; neither answer removes a transaction.
      </CardFoot>
    </Card>
  );
}

function PairSide({ side, label, onOpen }) {
  return (
    <div className="pair-side">
      <span className="pair-side-label">{label}</span>
      <button
        type="button"
        className="pair-side-open"
        onClick={() => onOpen(side.id)}
        title="Open this transaction"
      >
        <IconCopy size={13} />
        <span className="num">{formatDate(side.date)}</span>
      </button>
      <p className="pair-side-desc" title={side.description}>
        {shortenDescription(side.description, 64)}
      </p>
      <div className="pair-side-meta">
        <span className="num amount-out">{formatMoneyExact(side.amount)}</span>
        {side.payment_method && <span className="chip">{side.payment_method}</span>}
      </div>
    </div>
  );
}
