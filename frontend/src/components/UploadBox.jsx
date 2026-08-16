import { useRef, useState } from "react";

import {
  IconArrowRight,
  IconCheck,
  IconUpload,
} from "../icons.jsx";
import { navigate } from "../router.js";
import Button from "./ui/Button.jsx";
import Card from "./ui/Card.jsx";

/**
 * Drop statements here, or click to pick them.
 *
 * Several files at once is the normal case: bank portals export one file per
 * month, so a year of history arrives as twelve downloads. They import one
 * after another and the dashboard refreshes once at the end, rather than
 * redrawing twelve times.
 *
 * The result panel matters as much as the upload itself: re-uploading a
 * statement reports 0 imported and N duplicates, and without that sentence on
 * screen a correct no-op looks like a broken button.
 */
export default function UploadBox({ onUpload, busy, progress, lastResult }) {
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef(null);

  function handleFiles(fileList) {
    const files = Array.from(fileList || []);
    if (files.length > 0) onUpload(files);
  }

  // A real percentage across the batch — files done, plus the one in flight.
  const percent =
    progress && progress.total
      ? Math.round(((progress.current - 1) / progress.total) * 100)
      : 0;

  return (
    <Card>
      <div
        className={`dropzone ${dragging ? "dragging" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          if (!busy) handleFiles(event.dataTransfer.files);
        }}
      >
        {busy ? (
          <UploadingState progress={progress} percent={percent} />
        ) : (
          <>
            <div className="dropzone-icon">
              <IconUpload size={24} />
            </div>

            <h3>Drag &amp; drop your statement here</h3>
            <p>
              CSV, JSON or Excel. Several at once is fine, and every sheet in a
              workbook is read.
            </p>

            <input
              ref={fileInput}
              type="file"
              multiple
              accept=".csv,.tsv,.txt,.json,.xlsx,.xlsm,text/csv,application/json"
              className="visually-hidden"
              id="statement-file"
              onChange={(event) => {
                handleFiles(event.target.files);
                // Reset so choosing the same file twice fires onChange again.
                event.target.value = "";
              }}
            />

            <Button
              variant="primary"
              size="lg"
              onClick={() => fileInput.current?.click()}
            >
              Browse files
            </Button>

            <p style={{ marginTop: "var(--sp-4)", marginBottom: 0 }}>
              Re-uploading a file you already imported is safe — every row is
              recognised and reported as a duplicate.
            </p>
          </>
        )}
      </div>

      {!busy && lastResult && <UploadSummary result={lastResult} />}
    </Card>
  );
}

/**
 * What is happening, in the app's own terms.
 *
 * Only stages the backend actually performs are listed. A fake "Analysing with
 * AI…" step would be theatre, and the one stage that genuinely happens per
 * file — parse, dedupe, categorize — is a single request, so the honest
 * granularity is the file, not the phase.
 */
function UploadingState({ progress, percent }) {
  const many = progress && progress.total > 1;

  return (
    <div aria-live="polite">
      <div className="dropzone-icon">
        <span className="btn-spinner" style={{ width: 22, height: 22 }} />
      </div>

      <h3>{many ? `Importing ${progress.current} of ${progress.total}` : "Importing your statement"}</h3>
      <p>{progress?.filename}</p>

      <div style={{ maxWidth: 340, margin: "0 auto" }}>
        <div className="progress-track">
          <div
            className="progress-fill"
            style={{ width: many ? `${percent}%` : "100%" }}
          />
        </div>
      </div>

      <div className="upload-steps">
        <div className="upload-step done">
          <IconCheck size={14} /> File received
        </div>
        <div className="upload-step active">
          <span className="btn-spinner" style={{ width: 12, height: 12 }} />
          Parsing rows and skipping junk
        </div>
        <div className="upload-step active">
          <span className="btn-spinner" style={{ width: 12, height: 12 }} />
          Categorizing with rules, then the model
        </div>
      </div>
    </div>
  );
}

/**
 * One panel covering the whole batch.
 *
 * Failures are named individually — "3 files imported" while one silently
 * failed is exactly the report that hides a problem.
 */
function UploadSummary({ result }) {
  const { imported, duplicates, skipped, files, failures } = result;
  const fileWord = files === 1 ? "file" : "files";
  const nothingNew = imported === 0 && duplicates > 0;

  return (
    <div className="card-body" style={{ borderTop: "1px solid var(--border)" }}>
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: "var(--sp-3)",
        }}
      >
        <span
          className="state-icon"
          style={{
            width: 34,
            height: 34,
            background: imported > 0 ? "var(--success-soft)" : "var(--primary-soft)",
            color: imported > 0 ? "var(--success)" : "var(--primary)",
          }}
        >
          <IconCheck size={17} />
        </span>

        <div style={{ flex: 1, minWidth: 0 }}>
          <h3 style={{ fontSize: 14 }}>
            {imported > 0 ? "Upload complete" : "Upload succeeded"}
          </h3>

          <p className="prose" style={{ marginTop: 2 }}>
            {imported > 0
              ? `${imported.toLocaleString("en-IN")} transactions imported from ${files} ${fileWord}.`
              : nothingNew
                ? `Nothing changed — all ${duplicates.toLocaleString("en-IN")} rows in ` +
                  `${files === 1 ? "this file" : `these ${files} files`} were already in your data.`
                : `No transactions found in ${files} ${fileWord}.`}
            {imported > 0 && duplicates > 0 &&
              ` ${duplicates.toLocaleString("en-IN")} duplicates skipped.`}
            {skipped > 0 && ` ${skipped} unreadable rows skipped.`}
          </p>

          {failures.length > 0 && (
            <ul
              style={{
                margin: "var(--sp-3) 0 0",
                paddingLeft: 18,
                fontSize: 12.5,
                color: "var(--danger)",
              }}
            >
              {failures.map((failure) => (
                <li key={failure.filename}>
                  <strong>{failure.filename}</strong> — {failure.message}
                </li>
              ))}
            </ul>
          )}

          {imported > 0 && (
            <div style={{ marginTop: "var(--sp-4)", display: "flex", gap: "var(--sp-2)" }}>
              <Button
                variant="primary"
                size="sm"
                onClick={() => navigate("/transactions")}
              >
                View transactions
                <IconArrowRight size={14} />
              </Button>
              <Button variant="secondary" size="sm" onClick={() => navigate("/")}>
                Go to dashboard
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
