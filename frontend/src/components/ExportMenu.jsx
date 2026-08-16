import { useState } from "react";

import * as api from "../api.js";
import Button from "./ui/Button.jsx";
import { IconFile } from "../icons.jsx";

/**
 * Download buttons for whatever the page is currently showing.
 *
 * `params` is the same filter object the page already passes to the API, so an
 * export always matches what is on screen. An export that quietly ignores the
 * active filter is the fastest way to make someone distrust both the file and
 * the page it came from — which is why the caption below states the scope in
 * words rather than leaving it to be inferred.
 */
export default function ExportMenu({
  kind = "transactions",
  params = {},
  scopeLabel,
  onError,
  onSuccess,
}) {
  const [busy, setBusy] = useState(null);

  async function run(format) {
    setBusy(format);
    try {
      const exporter =
        kind === "summary" ? api.exportSummary : api.exportTransactions;
      const name = await exporter({ ...params, format });
      onSuccess(`Downloaded ${name}`);
    } catch (error) {
      onError(error);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="export-menu">
      <Button
        size="sm"
        variant="secondary"
        icon={IconFile}
        loading={busy === "csv"}
        disabled={busy !== null}
        onClick={() => run("csv")}
      >
        CSV
      </Button>
      <Button
        size="sm"
        variant="secondary"
        icon={IconFile}
        loading={busy === "xlsx"}
        disabled={busy !== null}
        onClick={() => run("xlsx")}
      >
        Excel
      </Button>
      {scopeLabel && <span className="export-scope">{scopeLabel}</span>}
    </div>
  );
}
