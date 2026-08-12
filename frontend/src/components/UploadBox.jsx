import { useRef, useState } from "react";

/**
 * Drop statements here, or click to pick them.
 *
 * Several files at once is the normal case: bank portals export one file per
 * month, so a year of history arrives as twelve downloads. They import one
 * after another and the dashboard refreshes once at the end, rather than
 * redrawing twelve times.
 *
 * The result line matters as much as the upload: re-uploading a statement
 * reports 0 imported and N duplicates, and without that sentence on screen a
 * correct no-op looks like a broken button.
 */
export default function UploadBox({ onUpload, busy, progress, lastResult }) {
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef(null);

  function handleFiles(fileList) {
    const files = Array.from(fileList || []);
    if (files.length > 0) {
      onUpload(files);
    }
  }

  return (
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
        handleFiles(event.dataTransfer.files);
      }}
    >
      <p>
        Drop bank statements here — CSV, JSON or Excel.
        <br />
        Several at once is fine, and every sheet in a workbook is read.
      </p>

      <input
        ref={fileInput}
        type="file"
        multiple
        accept=".csv,.tsv,.txt,.json,.xlsx,.xlsm,text/csv,application/json"
        style={{ display: "none" }}
        onChange={(event) => {
          handleFiles(event.target.files);
          // Reset so choosing the same file twice fires onChange again.
          event.target.value = "";
        }}
      />

      <button
        className="primary"
        onClick={() => fileInput.current.click()}
        disabled={busy}
      >
        {busy ? "Importing…" : "Choose files"}
      </button>

      {busy && progress && progress.total > 1 && (
        <p className="chart-note">
          Importing {progress.current} of {progress.total}: {progress.filename}
        </p>
      )}

      {!busy && lastResult && <UploadSummary result={lastResult} />}
    </div>
  );
}

/**
 * One line covering the whole batch.
 *
 * Failures are named individually — "3 files imported" while one silently
 * failed is exactly the report that hides a problem.
 */
function UploadSummary({ result }) {
  const { imported, duplicates, skipped, files, failures } = result;
  const fileWord = files === 1 ? "file" : "files";

  const nothingNew = imported === 0 && duplicates > 0;

  return (
    <div className="chart-note">
      <p style={{ margin: 0 }}>
        {imported > 0
          ? `Imported ${imported} transactions from ${files} ${fileWord}.`
          : nothingNew
            ? `Upload succeeded, but nothing changed — all ${duplicates} rows in ` +
              `${files === 1 ? "this file" : `these ${files} files`} were already ` +
              `in your data.`
            : `No transactions found in ${files} ${fileWord}.`}
        {imported > 0 && duplicates > 0 && ` ${duplicates} duplicates skipped.`}
        {skipped > 0 && ` ${skipped} unreadable rows skipped.`}
      </p>

      {failures.length > 0 && (
        <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
          {failures.map((failure) => (
            <li key={failure.filename}>
              <strong>{failure.filename}</strong> — {failure.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
