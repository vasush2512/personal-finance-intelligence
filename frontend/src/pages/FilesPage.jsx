import { useState } from "react";

import UploadBox from "../components/UploadBox.jsx";
import { encodeSource } from "../components/Filters.jsx";
import { formatDate } from "../format.js";
import { navigate } from "../router.js";

/**
 * Everything that has been imported, and the way back out.
 *
 * Deleting an upload is the undo button for a bad import. Without it the
 * only remedy is deleting the database file, which takes the good data with
 * it — so the destructive action is here, behind a confirmation, rather than
 * left to the API docs.
 */
export default function FilesPage({
  sources,
  onUpload,
  uploading,
  uploadProgress,
  lastUpload,
  onDelete,
  filters,
  onFilterChange,
}) {
  const [confirming, setConfirming] = useState(null);

  function viewSource(uploadId, sheetName) {
    onFilterChange({ ...filters, source: encodeSource(uploadId, sheetName) });
    navigate("/transactions");
  }

  return (
    <>
      <UploadBox
        onUpload={onUpload}
        busy={uploading}
        progress={uploadProgress}
        lastResult={lastUpload}
      />

      <div className="card">
        <h2>Imported files</h2>

        {sources.length === 0 ? (
          <p className="chart-note">
            Nothing imported yet. Upload a statement above.
          </p>
        ) : (
          sources.map((source) => (
            <div className="file-row" key={source.upload_id}>
              <div className="file-main">
                <div className="file-name">{source.filename}</div>
                <div className="file-meta">
                  {source.count.toLocaleString("en-IN")} transactions ·
                  imported {formatDate(source.uploaded_at.slice(0, 10))}
                </div>

                <div className="file-sheets">
                  {source.sheets.map((sheet) => (
                    <button
                      key={sheet.sheet_name || "__none__"}
                      className="chip"
                      onClick={() => viewSource(source.upload_id, sheet.sheet_name)}
                    >
                      {sheet.sheet_name || "All rows"} ({sheet.count.toLocaleString("en-IN")})
                    </button>
                  ))}
                </div>
              </div>

              <div className="file-actions">
                <button onClick={() => viewSource(source.upload_id)}>View</button>

                {confirming === source.upload_id ? (
                  <>
                    <button
                      className="danger"
                      onClick={() => {
                        setConfirming(null);
                        onDelete(source.upload_id, source.filename);
                      }}
                    >
                      Delete {source.count.toLocaleString("en-IN")} rows
                    </button>
                    <button onClick={() => setConfirming(null)}>Cancel</button>
                  </>
                ) : (
                  <button onClick={() => setConfirming(source.upload_id)}>
                    Delete
                  </button>
                )}
              </div>
            </div>
          ))
        )}

        <p className="chart-note">
          Deleting a file removes its transactions too, and frees them to be
          imported again. Corrections you made to those rows go with them.
        </p>
      </div>
    </>
  );
}
