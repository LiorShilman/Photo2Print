// S-6 — היסטוריית ג'ובים
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, thumbnailArtifact, type Job } from "../api";
import { IconCube, IconImage } from "../components/icons";
import Select from "../components/Select";

type StatusFilter = "all" | "done" | "failed" | "waiting" | "working";

function statusGroup(status: string): StatusFilter {
  if (status === "done") return "done";
  if (status === "failed") return "failed";
  if (status.startsWith("awaiting")) return "waiting";
  return "working";
}

export default function HistoryPage() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<StatusFilter>("all");
  const { data: jobs } = useQuery({ queryKey: ["jobs"], queryFn: api.listJobs });
  const del = useMutation({
    mutationFn: api.deleteJob,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
  const dup = useMutation({ mutationFn: api.duplicate,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }) });
  const delAll = useMutation({
    mutationFn: async (ids: string[]) => { await Promise.all(ids.map((id) => api.deleteJob(id))); },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });

  const filtered = useMemo<Job[]>(
    () => (jobs ?? []).filter((j) => filter === "all" || statusGroup(j.status) === filter),
    [jobs, filter],
  );

  return (
    <>
      <div className="row" style={{ alignItems: "baseline", justifyContent: "space-between" }}>
        <h1>היסטוריית ג'ובים</h1>
        <div className="row" style={{ gap: "0.6rem", alignItems: "center" }}>
          <Select value={filter} onChange={(v) => setFilter(v as StatusFilter)}
                  options={[
                    { value: "all", label: "כל הסטטוסים" },
                    { value: "done", label: "הושלמו" },
                    { value: "failed", label: "נכשלו" },
                    { value: "waiting", label: "ממתינים" },
                    { value: "working", label: "בעיבוד" },
                  ]} />
          {filtered.length > 0 && (
            <button className="danger" disabled={delAll.isPending}
                    onClick={() => {
                      if (confirm(`למחוק ${filtered.length} ג'ובים? כל הקבצים שלהם יימחקו לצמיתות.`)) {
                        delAll.mutate(filtered.map((j) => j.id));
                      }
                    }}>
              {delAll.isPending ? "מוחק…" : `מחק הכל (${filtered.length})`}
            </button>
          )}
        </div>
      </div>
      <table className="jobs">
        <thead>
          <tr><th></th><th>מזהה</th><th>תאריך</th><th>סוג קלט</th><th>מדפסת</th><th>סטטוס</th><th>פעולות</th></tr>
        </thead>
        <tbody>
          {filtered.map((j) => {
            const preview = thumbnailArtifact(j);
            return (
              <tr key={j.id}>
                <td>{preview
                  ? <img src={api.artifactUrl(preview.id)} width={44} height={44} style={{ borderRadius: 8, objectFit: "cover" }} />
                  : <span style={{ color: "#4a5170" }}>{j.input_type === "mesh" ? <IconCube size={26} /> : <IconImage size={26} />}</span>}</td>
                <td><Link to={`/jobs/${j.id}`} className="mono" style={{ color: "var(--accent)" }}>{j.id}</Link></td>
                <td className="muted">{new Date(j.created_at).toLocaleString("he-IL")}</td>
                <td>{{ image: "תמונה", multi_image: "ריבוי תמונות", mesh: "קובץ 3D" }[j.input_type] ?? j.input_type}</td>
                <td className="muted">{j.print_stats_json?.profile ?? "—"}</td>
                <td><span className={`badge ${statusGroup(j.status)}`}>{j.status}</span></td>
                <td>
                  <div className="row" style={{ gap: "0.4rem" }}>
                    {j.status === "done" && <a className="btn secondary" style={{ padding: "0.25rem 0.7rem", fontSize: "0.82rem" }} href={api.downloadUrl(j.id)}>הורדה</a>}
                    <button className="secondary" style={{ padding: "0.25rem 0.7rem", fontSize: "0.82rem" }}
                            onClick={() => dup.mutate(j.id)}>שכפול</button>
                    <button className="danger" style={{ padding: "0.25rem 0.7rem", fontSize: "0.82rem" }}
                            onClick={() => { if (confirm(`למחוק את ${j.id}? כל הקבצים יימחקו.`)) del.mutate(j.id); }}>מחיקה</button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {jobs?.length === 0 && <p className="muted">אין עדיין ג'ובים. <Link to="/" style={{ color: "var(--accent)" }}>צור אחד →</Link></p>}
      {(jobs?.length ?? 0) > 0 && filtered.length === 0 && <p className="muted">אין ג'ובים בסטטוס הזה.</p>}
    </>
  );
}
