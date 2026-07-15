// S-3 + S-4 + S-5 — מסך הג'וב: המתנה חכמה → כיוונון → תוצאות
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, latestArtifact, type Job } from "../api";
import { useJobProgress } from "../hooks/useJobProgress";
import Viewer3D from "../components/Viewer3D";
import GatesRow from "../components/GatesRow";

const STAGE_HE: [string, string][] = [
  ["ingest", "קליטה ואימות"],
  ["preprocess", "עיבוד תמונה"],
  ["mesh_generation", "יצירת מודל"],
  ["mesh_repair", "תיקון רשת"],
  ["scale_orient", "סקייל וכיוון"],
  ["quality_gates", "שערי איכות"],
  ["slicing", "Slicing"],
  ["package", "אריזה"],
];

const WORKING = ["pending", "running", "orienting", "slicing"];

export default function JobPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const progress = useJobProgress(id);

  const { data: job } = useQuery({
    queryKey: ["job", id],
    queryFn: () => api.getJob(id!),
    enabled: !!id,
    refetchInterval: (q) => (WORKING.includes(q.state.data?.status ?? "") ? 3000 : false),
  });

  if (!job) return <p className="muted">טוען…</p>;

  const working = WORKING.includes(job.status);

  return (
    <>
      <div className="row">
        <h1 className="grow">ג'וב <span className="mono">{job.id}</span></h1>
        <StatusBadge status={job.status} />
      </div>
      <GatesRow gates={job.gates_json} />

      {job.status === "failed" && <FailedView job={job} />}
      {working && <ProgressView job={job} progressPct={progress?.progress_pct ?? 0}
                                message={progress?.message_he ?? "מעבד…"} />}
      {job.status === "awaiting_scale" && <ScaleView job={job} />}
      {job.status === "awaiting_slice" && <SliceView job={job} />}
      {job.status === "done" && <ResultsView job={job} />}
    </>
  );
}

function StatusBadge({ status }: { status: string }) {
  const cls = status === "done" ? "done" : status === "failed" ? "failed"
    : status.startsWith("awaiting") ? "waiting" : "working";
  const text: Record<string, string> = {
    pending: "ממתין", running: "מעבד", awaiting_scale: "ממתין למידות",
    orienting: "מכוון", awaiting_slice: "מוכן ל-Slicing", slicing: "פורס שכבות",
    done: "הושלם", failed: "נכשל",
  };
  return <span className={`badge ${cls}`}>{text[status] ?? status}</span>;
}

// --- S-3: מסך המתנה חכם ---
function ProgressView({ job, progressPct, message }: { job: Job; progressPct: number; message: string }) {
  const stageStatus = useMemo(() => {
    const m = new Map(job.stages.map((s) => [s.stage_name, s.status]));
    return STAGE_HE.map(([key, label]) => ({ key, label, status: m.get(key) ?? "pending" }));
  }, [job.stages]);

  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>{message}</h3>
      <div className="progress-track"><div className="progress-fill" style={{ width: `${progressPct}%` }} /></div>
      <ul className="stage-list">
        {stageStatus.map((s) => (
          <li key={s.key} className={s.status === "done" ? "done" : s.status === "running" ? "running" : s.status === "failed" ? "failed" : ""}>
            {s.status === "done" ? "✔" : s.status === "running" ? "◌" : s.status === "failed" ? "✘" : "·"} {s.label}
          </li>
        ))}
      </ul>
    </div>
  );
}

function FailedView({ job }: { job: Job }) {
  const failedStage = job.stages.find((s) => s.status === "failed");
  const suggestions = (failedStage?.error_json?.suggestions_he as string[] | undefined) ?? [];
  const qc = useQueryClient();
  const dup = useMutation({ mutationFn: () => api.duplicate(job.id) });

  return (
    <div className="error-box">
      <b>העיבוד נעצר:</b> {job.error_he}
      {suggestions.length > 0 && (
        <ul>{suggestions.map((s, i) => <li key={i}>{s}</li>)}</ul>
      )}
      <div className="row" style={{ marginTop: "0.8rem" }}>
        <button className="secondary" onClick={() => dup.mutate()}>🔁 נסה שוב (ג'וב חדש)</button>
        {dup.data && <a className="btn" href={`/jobs/${dup.data.id}`}>לג'וב החדש</a>}
      </div>
    </div>
  );
}

// --- S-4: סקייל וכיוון ---
function ScaleView({ job }: { job: Job }) {
  const [axis, setAxis] = useState<"x" | "y" | "z">("z");
  const [sizeMm, setSizeMm] = useState(80);
  const [autoOrient, setAutoOrient] = useState(true);
  const [flatten, setFlatten] = useState(false);
  const qc = useQueryClient();
  const { data: profiles } = useQuery({ queryKey: ["profiles"], queryFn: api.listProfiles });
  const [profileId, setProfileId] = useState<string>("");

  const mesh = latestArtifact(job, "mesh_repaired");
  const profile = profiles?.find((p) => p.id === (profileId || job.profile_id));

  const scale = useMutation({
    mutationFn: () => api.scale(job.id, {
      axis, size_mm: sizeMm, auto_orient: autoOrient, flatten_base: flatten,
      rotation_deg: [0, 0, 0],
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["job", job.id] }),
  });

  return (
    <div className="viewer-layout">
      {mesh && (
        <Viewer3D stlUrl={api.artifactUrl(mesh.id)} targetHeightMm={sizeMm} scaleAxis={axis}
                  bed={profile ? { x: profile.bed_x, y: profile.bed_y, z: profile.bed_z } : undefined} />
      )}
      <div className="side-panel">
        <div className="card">
          <h3 style={{ marginTop: 0 }}>📐 קביעת מידות</h3>
          <label>ציר מוביל</label>
          <select value={axis} onChange={(e) => setAxis(e.target.value as "x" | "y" | "z")}>
            <option value="z">גובה (Z)</option>
            <option value="x">רוחב (X)</option>
            <option value="y">עומק (Y)</option>
          </select>
          <label style={{ marginTop: "0.7rem" }}>מידה במ"מ</label>
          <input type="number" min={5} max={500} value={sizeMm}
                 onChange={(e) => setSizeMm(Number(e.target.value))} style={{ width: "100%" }} />
          <input type="range" min={10} max={300} value={sizeMm}
                 onChange={(e) => setSizeMm(Number(e.target.value))} style={{ width: "100%" }} />
          <label style={{ marginTop: "0.7rem" }}>מדפסת (לבדיקת נפח)</label>
          <select value={profileId || job.profile_id || ""} onChange={(e) => setProfileId(e.target.value)}>
            <option value="">— ללא —</option>
            {profiles?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <div style={{ marginTop: "0.8rem" }}>
            <label><input type="checkbox" checked={autoOrient} onChange={(e) => setAutoOrient(e.target.checked)} /> אוריינטציה אוטומטית (ממזער supports)</label>
            <label><input type="checkbox" checked={flatten} onChange={(e) => setFlatten(e.target.checked)} /> השטחת בסיס עדינה</label>
          </div>
          <button style={{ width: "100%", marginTop: "1rem" }}
                  disabled={scale.isPending || sizeMm <= 0}
                  onClick={() => scale.mutate()}>
            {scale.isPending ? "מעבד…" : "המשך →"}
          </button>
          {scale.isError && <p style={{ color: "var(--error)" }}>{(scale.error as Error).message}</p>}
        </div>
        {job.ai_confidence != null && job.source_provider !== "user_upload" && (
          <div className="card muted" style={{ fontSize: "0.88rem" }}>
            ספק: <b>{job.source_provider}</b> · ביטחון: <b>{(job.ai_confidence * 100).toFixed(0)}%</b>
            {job.image_score != null && <> · ציון תמונה: <b>{job.image_score}</b></>}
          </div>
        )}
      </div>
    </div>
  );
}

// --- S-4b: בחירת slicing ---
function SliceView({ job }: { job: Job }) {
  const qc = useQueryClient();
  const { data: profiles } = useQuery({ queryKey: ["profiles"], queryFn: api.listProfiles });
  const [profileId, setProfileId] = useState(job.profile_id ?? "");
  const [preset, setPreset] = useState<"draft" | "standard" | "quality">("standard");
  const [material, setMaterial] = useState<"PLA" | "PETG" | "TPU">("PLA");
  const [advanced, setAdvanced] = useState(false);
  const [adv, setAdv] = useState({ infill_pct: 15, supports: "auto", brim: false });

  const mesh = latestArtifact(job, "mesh_final") ?? latestArtifact(job, "mesh_repaired");
  const profile = profiles?.find((p) => p.id === profileId);

  const slice = useMutation({
    mutationFn: () => api.slice(job.id, {
      profile_id: profileId, preset, material,
      advanced: advanced ? { infill_pct: adv.infill_pct, supports: adv.supports, brim: adv.brim } : null,
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["job", job.id] }),
  });

  return (
    <div className="viewer-layout">
      {mesh && (
        <Viewer3D stlUrl={api.artifactUrl(mesh.id)}
                  bed={profile ? { x: profile.bed_x, y: profile.bed_y, z: profile.bed_z } : undefined} />
      )}
      <div className="side-panel">
        <div className="card">
          <h3 style={{ marginTop: 0 }}>🔪 הגדרות Slicing</h3>
          <label>מדפסת</label>
          <select value={profileId} onChange={(e) => setProfileId(e.target.value)} style={{ width: "100%" }}>
            <option value="">בחר מדפסת…</option>
            {profiles?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <label style={{ marginTop: "0.7rem" }}>פריסט איכות</label>
          <select value={preset} onChange={(e) => setPreset(e.target.value as typeof preset)} style={{ width: "100%" }}>
            <option value="draft">Draft — 0.28 מ"מ (מהיר)</option>
            <option value="standard">Standard — 0.2 מ"מ</option>
            <option value="quality">Quality — 0.12 מ"מ (איטי ומדויק)</option>
          </select>
          <label style={{ marginTop: "0.7rem" }}>חומר</label>
          <select value={material} onChange={(e) => setMaterial(e.target.value as typeof material)} style={{ width: "100%" }}>
            <option>PLA</option><option>PETG</option><option>TPU</option>
          </select>

          <label style={{ marginTop: "0.9rem" }}>
            <input type="checkbox" checked={advanced} onChange={(e) => setAdvanced(e.target.checked)} /> מצב Advanced
          </label>
          {advanced && (
            <div style={{ background: "var(--bg)", borderRadius: 10, padding: "0.8rem", marginTop: "0.5rem" }}>
              <label>Infill: {adv.infill_pct}%</label>
              <input type="range" min={0} max={60} value={adv.infill_pct}
                     onChange={(e) => setAdv({ ...adv, infill_pct: Number(e.target.value) })} style={{ width: "100%" }} />
              <label style={{ marginTop: "0.5rem" }}>Supports</label>
              <select value={adv.supports} onChange={(e) => setAdv({ ...adv, supports: e.target.value })} style={{ width: "100%" }}>
                <option value="auto">אוטומטי</option>
                <option value="tree">Tree (אורגני)</option>
                <option value="off">כבוי</option>
              </select>
              <label style={{ marginTop: "0.5rem" }}>
                <input type="checkbox" checked={adv.brim} onChange={(e) => setAdv({ ...adv, brim: e.target.checked })} /> Brim (הצמדות)
              </label>
            </div>
          )}

          <button style={{ width: "100%", marginTop: "1rem" }}
                  disabled={!profileId || slice.isPending}
                  onClick={() => slice.mutate()}>
            {slice.isPending ? "פורס…" : "▶ הרץ Slicing"}
          </button>
          {slice.isError && <p style={{ color: "var(--error)" }}>{(slice.error as Error).message}</p>}
        </div>
      </div>
    </div>
  );
}

// --- S-5: תוצאות ---
function ResultsView({ job }: { job: Job }) {
  const stats = job.print_stats_json;
  const previews = job.artifacts.filter((a) => a.kind === "preview");
  const report = latestArtifact(job, "report");
  const gcode = latestArtifact(job, "gcode");
  const mesh = latestArtifact(job, "mesh_final");
  const qc = useQueryClient();
  const reslice = useMutation({
    mutationFn: () => api.getJob(job.id),
    onSuccess: async () => {
      await fetch(`/api/v1/jobs/${job.id}`); // no-op — הכפתור מוביל ל-SliceView דרך שינוי סטטוס בשרת
    },
  });
  const [showSlice, setShowSlice] = useState(false);

  const t = stats?.time_s ?? 0;
  const timeStr = t >= 3600 ? `${Math.floor(t / 3600)}:${String(Math.floor((t % 3600) / 60)).padStart(2, "0")} שע'` : `${Math.round(t / 60)} דק'`;

  return (
    <>
      <div className="stat-cards">
        <div className="stat-card"><b>{timeStr}</b><span>⏱ זמן הדפסה</span></div>
        <div className="stat-card"><b>{stats?.filament_g?.toFixed(0) ?? "?"} גרם</b><span>🧵 חוט</span></div>
        <div className="stat-card"><b>₪{stats?.cost?.total_ils ?? "?"}</b><span>💰 עלות משוערת</span></div>
        <div className="stat-card"><b>{stats?.layers ?? "?"}</b><span>🥞 שכבות</span></div>
      </div>

      <div className="row" style={{ margin: "1rem 0" }}>
        <a className="btn" href={api.downloadUrl(job.id)}>⬇️ הורד חבילה מלאה (ZIP)</a>
        {gcode && <a className="btn secondary" style={{ background: "var(--surface2)", color: "var(--text)" }} href={api.artifactUrl(gcode.id)}>G-code בלבד</a>}
        {mesh && <a className="btn secondary" style={{ background: "var(--surface2)", color: "var(--text)" }} href={api.artifactUrl(mesh.id)}>STL בלבד</a>}
        {report && <a className="btn secondary" style={{ background: "var(--surface2)", color: "var(--text)" }} href={api.artifactUrl(report.id)} target="_blank">📄 דוח מלא</a>}
        <button className="secondary" onClick={() => setShowSlice(true)}>🔁 שכפל עם פרופיל אחר</button>
      </div>

      {showSlice && <SliceView job={job} />}

      {previews.length > 0 && (
        <>
          <h2>תצוגות מקדימות</h2>
          <div className="stat-cards">
            {previews.map((p) => (
              <img key={p.id} src={api.artifactUrl(p.id)} alt={p.filename}
                   style={{ width: "100%", borderRadius: 12, border: "1px solid var(--border)" }} />
            ))}
          </div>
        </>
      )}

      {mesh && (
        <>
          <h2>המודל הסופי</h2>
          <Viewer3D stlUrl={api.artifactUrl(mesh.id)} />
        </>
      )}
    </>
  );
}
