import { useRef, useState } from "react";

/**
 * Drop a CSV here, or click to pick one.
 *
 * The result line matters as much as the upload: re-uploading a statement
 * reports 0 imported and N duplicates, and without that sentence on screen
 * a correct no-op looks like a broken button.
 */
export default function UploadBox({ onUpload, busy, lastResult }) {
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef(null);

  function handleFiles(files) {
    if (files && files.length > 0) {
      onUpload(files[0]);
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
      <p>Drop a bank statement CSV here</p>

      <input
        ref={fileInput}
        type="file"
        accept=".csv,text/csv"
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
        {busy ? "Importing…" : "Choose a file"}
      </button>

      {lastResult && (
        <p className="chart-note">
          {lastResult.imported > 0
            ? `Imported ${lastResult.imported} transactions from ${lastResult.filename}.`
            : `Nothing new in ${lastResult.filename} — every row was already imported.`}
          {lastResult.duplicates > 0 && ` ${lastResult.duplicates} duplicates skipped.`}
          {lastResult.skipped > 0 && ` ${lastResult.skipped} unreadable rows skipped.`}
        </p>
      )}
    </div>
  );
}
