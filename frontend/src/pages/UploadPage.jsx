import { useState } from "react";

import UploadBox from "../components/UploadBox.jsx";
import { encodeSource } from "../components/Filters.jsx";
import Card, { CardHead, CardFoot } from "../components/ui/Card.jsx";
import Button from "../components/ui/Button.jsx";
import ConfirmDialog from "../components/ui/Modal.jsx";
import { EmptyState } from "../components/ui/Feedback.jsx";
import { IconFile, IconTrash } from "../icons.jsx";
import { formatDate } from "../format.js";
import { navigate } from "../router.js";

/**
 * Upload statements, and manage what has already been imported.
 *
 * Deleting an upload is the undo button for a bad import. Without it the only
 * remedy is deleting the database file, which takes the good data with it — so
 * the destructive action is here, behind a dialog that says exactly how many
 * rows are about to go.
 */
export default function UploadPage({
  sources,
  onUpload,
  uploading,
  uploadProgress,
  lastUpload,
  onDelete,
  filters,
  onFilterChange,
}) {
  const [pendingDelete, setPendingDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);

  function viewSource(uploadId, sheetName) {
    onFilterChange({ ...filters, source: encodeSource(uploadId, sheetName) });
    navigate("/transactions");
  }

  async function confirmDelete() {
    setDeleting(true);
    try {
      await onDelete(pendingDelete.upload_id, pendingDelete.filename);
      setPendingDelete(null);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="stack">
      <UploadBox
        onUpload={onUpload}
        busy={uploading}
        progress={uploadProgress}
        lastResult={lastUpload}
      />

      <Card>
        <CardHead
          title="Upload history"
          description={
            sources.length > 0
              ? `${sources.length} file${sources.length === 1 ? "" : "s"} currently contributing transactions`
              : undefined
          }
          bordered
        />

        {sources.length === 0 ? (
          <EmptyState
            icon={IconFile}
            title="No files imported yet"
            description="Upload a statement above. There is a sample at backend/data/sample_statement.csv if you want to try it first."
          />
        ) : (
          sources.map((source) => (
            <div className="file-row" key={source.upload_id}>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div className="file-name">
                  <IconFile size={15} />
                  {source.filename}
                </div>
                <div className="file-meta">
                  {source.count.toLocaleString("en-IN")} transactions · imported{" "}
                  {formatDate(source.uploaded_at.slice(0, 10))}
                </div>

                {/* One chip per worksheet. A workbook with a tab per month is
                    filterable tab by tab, which is why the sheet names are
                    stored at all. */}
                <div className="chips">
                  {source.sheets.map((sheet) => (
                    <button
                      key={sheet.sheet_name || "__none__"}
                      className="chip"
                      onClick={() => viewSource(source.upload_id, sheet.sheet_name)}
                    >
                      {sheet.sheet_name || "All rows"} (
                      {sheet.count.toLocaleString("en-IN")})
                    </button>
                  ))}
                </div>
              </div>

              <div className="file-actions">
                <Button size="sm" onClick={() => viewSource(source.upload_id)}>
                  View
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  icon={IconTrash}
                  aria-label={`Delete ${source.filename}`}
                  onClick={() => setPendingDelete(source)}
                />
              </div>
            </div>
          ))
        )}

        <CardFoot>
          Deleting a file removes its transactions too, and frees them to be
          imported again. Corrections you made to those rows go with them.
        </CardFoot>
      </Card>

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        tone="danger"
        title="Delete this upload?"
        confirmLabel={
          pendingDelete
            ? `Delete ${pendingDelete.count.toLocaleString("en-IN")} transactions`
            : "Delete"
        }
        busy={deleting}
        onCancel={() => setPendingDelete(null)}
        onConfirm={confirmDelete}
      >
        <p>
          <strong>{pendingDelete?.filename}</strong> and all{" "}
          {pendingDelete?.count.toLocaleString("en-IN")} transactions that came
          from it will be permanently removed.
        </p>
        <p style={{ marginTop: "var(--sp-3)" }}>
          Any categories you corrected on those rows will be lost too. You can
          re-upload the file afterwards.
        </p>
      </ConfirmDialog>
    </div>
  );
}
