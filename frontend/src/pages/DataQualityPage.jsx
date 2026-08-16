import { useState } from "react";

import * as api from "../api.js";
import { decodeSource } from "../components/Filters.jsx";
import { StatCard } from "../components/StatCard.jsx";
import Card, { CardBody, CardFoot, CardHead } from "../components/ui/Card.jsx";
import Button from "../components/ui/Button.jsx";
import ConfirmDialog from "../components/ui/Modal.jsx";
import { ErrorState, StatSkeleton, TableSkeleton } from "../components/ui/Feedback.jsx";
import {
  IconAlert,
  IconCheckCircle,
  IconDatabase,
  IconShield,
} from "../icons.jsx";
import useResource from "../useResource.js";

/**
 * What is wrong, missing or odd about the imported rows.
 *
 * Several of the stranger numbers elsewhere in this app turn out to be data
 * problems wearing an analysis costume — spending that reads as zero because a
 * file had no debit/credit column, a category that dominates because nothing
 * recognised half the merchants. This page names them in one place rather than
 * leaving each to be rediscovered on the screen it happens to distort.
 *
 * Checks that found nothing are shown too. A list that hides them cannot tell
 * you the difference between "checked, fine" and "never checked".
 *
 * Only one issue offers a fix, and it runs from a button behind a confirmation
 * — never on load. A tool that quietly rewrites someone's rows to make its own
 * dashboard look healthier is the opposite of a data quality tool.
 */
export default function DataQualityPage({
  source,
  dataVersion,
  onError,
  onSuccess,
  onFixed,
}) {
  // Scoped to the selected statement. Reading a quality report about every
  // file while the rest of the app shows one is worse than no report: the
  // counts describe rows that are not on screen.
  const report = useResource(
    () => api.getDataQuality(decodeSource(source)),
    [source, dataVersion]
  );
  const [fixing, setFixing] = useState(null);
  const [confirming, setConfirming] = useState(null);

  async function runFix(issue) {
    setConfirming(null);
    setFixing(issue.key);
    try {
      const result = await api.fixDataQuality(issue.key, decodeSource(source));
      onSuccess(
        `${result.rows_changed.toLocaleString("en-IN")} rows corrected. ` +
          `Nothing else about them was changed.`
      );
      report.reload();
      // Coverage figures elsewhere are computed from this column, so they are
      // now out of date on every other page.
      if (onFixed) await onFixed();
    } catch (error) {
      onError(error);
    } finally {
      setFixing(null);
    }
  }

  if (report.loading && !report.data) {
    return (
      <div className="stack">
        <StatSkeleton count={3} />
        <TableSkeleton rows={5} />
      </div>
    );
  }

  if (report.error) {
    return (
      <Card>
        <ErrorState
          title="We couldn't check your data"
          error={report.error}
          onRetry={report.reload}
        />
      </Card>
    );
  }

  const data = report.data;
  const clean = data.issues_found === 0;

  return (
    <div className="stack">
      <div className="grid-4">
        <StatCard
          label="Transactions checked"
          value={data.total_transactions.toLocaleString("en-IN")}
          note={`Across ${data.checks_run} checks`}
          icon={IconDatabase}
          tone="primary"
        />
        <StatCard
          label="Checks that found something"
          value={`${data.issues_found} of ${data.checks_run}`}
          note={clean ? "Nothing to look at" : "Listed below, worst first"}
          icon={clean ? IconCheckCircle : IconAlert}
          tone={clean ? "success" : data.issues_found > 2 ? "danger" : "neutral"}
        />
        <StatCard
          label="Fixable automatically"
          value={data.issues.filter((issue) => issue.fix_label).length}
          note="The rest need a decision or a corrected file"
          icon={IconShield}
        />
      </div>

      {data.issues.map((issue) => (
        <IssueCard
          key={issue.key}
          issue={issue}
          busy={fixing === issue.key}
          disabled={fixing !== null}
          onFix={() => setConfirming(issue)}
        />
      ))}

      <Card>
        <CardHead title="Why this page does not fix things by itself" />
        <CardBody>
          <p className="prose">
            Every check here reads your data and changes nothing. Only one issue
            has a repair safe enough to offer — relabelling rows that claim a
            keyword rule matched them when no rule produces that category — and
            even that runs only when you press the button.
          </p>
          <p className="prose">
            Everything else needs either a decision only you can make, or a
            statement re-exported with the missing column. Rewriting rows to
            make a dashboard look healthier would make every figure in this app
            less trustworthy, not more.
          </p>
        </CardBody>
        <CardFoot>
          Amounts, dates, descriptions and categories are never modified by
          anything on this page.
        </CardFoot>
      </Card>

      <ConfirmDialog
        open={Boolean(confirming)}
        title="Correct these labels?"
        confirmLabel={`Correct ${confirming?.count.toLocaleString("en-IN")} rows`}
        onCancel={() => setConfirming(null)}
        onConfirm={() => runFix(confirming)}
      >
        <p>
          This sets <code>category_source</code> to <code>none</code> on{" "}
          {confirming?.count.toLocaleString("en-IN")} rows that say a keyword
          rule labelled them when none did.
        </p>
        <p style={{ marginTop: "var(--sp-3)" }}>
          Categories, amounts, dates and descriptions are not touched. Coverage
          figures on the Model page will not change — they already count these
          rows correctly. What changes is that the stored column stops
          disagreeing with them.
        </p>
      </ConfirmDialog>
    </div>
  );
}

const TONES = { high: "danger", medium: "warning", low: "success" };
const LABELS = { high: "Needs attention", medium: "Worth a look", low: "Fine" };

function IssueCard({ issue, busy, disabled, onFix }) {
  const clean = issue.count === 0;

  return (
    <Card>
      <CardHead
        title={issue.title}
        description={issue.detail}
        bordered={Boolean(issue.note || issue.fix_label)}
        actions={
          <span className={`badge badge-${clean ? "success" : TONES[issue.severity]}`}>
            {clean ? "Clear" : `${issue.count.toLocaleString("en-IN")} · ${LABELS[issue.severity]}`}
          </span>
        }
      />

      {(issue.note || issue.fix_label) && (
        <CardBody>
          {issue.note && <p className="note">{issue.note}</p>}
          {issue.fix_label && (
            <div className="pair-actions" style={{ borderTop: "none", paddingTop: 0 }}>
              <Button
                variant="primary"
                loading={busy}
                disabled={disabled && !busy}
                onClick={onFix}
              >
                {issue.fix_label}
              </Button>
            </div>
          )}
        </CardBody>
      )}
    </Card>
  );
}
