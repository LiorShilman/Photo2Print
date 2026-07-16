// S-3 + S-4 + S-5 — מסך הג'וב: המתנה חכמה → כיוונון → תוצאות
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, getDefaultProfileId, latestArtifact, type Job } from "../api";
import { useJobProgress } from "../hooks/useJobProgress";
import Viewer3D from "../components/Viewer3D";
import GatesRow from "../components/GatesRow";
import GcodePreview from "../components/GcodePreview";
import Lightbox from "../components/Lightbox";
import Select from "../components/Select";

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
      <div className="row" style={{ alignItems: "baseline", marginBottom: "0.2rem" }}>
        <h1 style={{ fontSize: "1.45rem", margin: 0 }}>
          {{ done: "תוצאות הדפסה", failed: "העיבוד נעצר", awaiting_scale: "קביעת מידות",
             awaiting_slice: "הגדרות הדפסה" }[job.status] ?? "מעבד את המודל"}
        </h1>
        <StatusBadge status={job.status} />
        <span className="grow" />
        <span className="mono muted" style={{ fontSize: "0.8rem" }}>{job.id}</span>
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
  const errorJson = failedStage?.error_json as { gate?: string; suggestions_he?: string[] } | null;
  const suggestions = errorJson?.suggestions_he ?? [];
  const qc = useQueryClient();
  const dup = useMutation({ mutationFn: () => api.duplicate(job.id) });

  // QG5 (חריגה מהמשטח) — הצעת חיתוך אוטומטי לחלקים
  const isBedOverflow = errorJson?.gate === "QG5" && !!job.scale_json;
  const split = useMutation({
    mutationFn: () => api.scale(job.id, { ...job.scale_json, allow_split: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["job", job.id] }),
  });

  return (
    <div className="error-box">
      <b>העיבוד נעצר:</b> {job.error_he}
      {suggestions.length > 0 && (
        <ul>{suggestions.map((s, i) => <li key={i}>{s}</li>)}</ul>
      )}
      <div className="row" style={{ marginTop: "0.8rem" }}>
        {isBedOverflow && (
          <button onClick={() => split.mutate()} disabled={split.isPending}>
            {split.isPending ? "חותך…" : "חתוך לחלקים אוטומטית"}
          </button>
        )}
        <button className="secondary" onClick={() => dup.mutate()}>נסה שוב (ג'וב חדש)</button>
        {dup.data && <a className="btn" href={`/jobs/${dup.data.id}`}>לג'וב החדש</a>}
      </div>
      {split.isError && <p style={{ color: "var(--error)" }}>{(split.error as Error).message}</p>}
    </div>
  );
}

// --- S-4: סקייל וכיוון ---
function RotationControl({ label, value, onChange }: {
  label: string; value: number; onChange: (v: number) => void;
}) {
  // snap ל-15° (F-5.5)
  const step = (d: number) => onChange(((value + d) % 360 + 360) % 360);
  return (
    <div className="row" style={{ gap: "0.4rem", alignItems: "center" }}>
      <span className="mono" style={{ width: 18 }}>{label}</span>
      <button className="secondary" style={{ padding: "0.15rem 0.55rem" }} onClick={() => step(-15)}>−15°</button>
      <span className="mono" style={{ width: 42, textAlign: "center" }}>{value}°</span>
      <button className="secondary" style={{ padding: "0.15rem 0.55rem" }} onClick={() => step(15)}>+15°</button>
    </div>
  );
}

function ScaleView({ job }: { job: Job }) {
  const [axis, setAxis] = useState<"x" | "y" | "z">("z");
  const [sizeMm, setSizeMm] = useState(80);
  const [autoOrient, setAutoOrient] = useState(true);
  const [flatten, setFlatten] = useState(false);
  const [rot, setRot] = useState<[number, number, number]>([0, 0, 0]);
  const qc = useQueryClient();
  const { data: profiles } = useQuery({ queryKey: ["profiles"], queryFn: api.listProfiles });
  const [profileId, setProfileId] = useState<string>(job.profile_id || getDefaultProfileId());

  const mesh = latestArtifact(job, "mesh_repaired");
  const profile = profiles?.find((p) => p.id === (profileId || job.profile_id));

  const scale = useMutation({
    mutationFn: () => api.scale(job.id, {
      axis, size_mm: sizeMm, auto_orient: autoOrient, flatten_base: flatten,
      rotation_deg: rot,
      profile_id: profileId || job.profile_id || null,
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["job", job.id] }),
  });

  return (
    <div className="viewer-layout">
      {mesh && (
        <Viewer3D stlUrl={api.artifactUrl(mesh.id)} targetHeightMm={sizeMm} scaleAxis={axis}
                  rotationDeg={rot}
                  bed={profile ? { x: profile.bed_x, y: profile.bed_y, z: profile.bed_z } : undefined} />
      )}
      <div className="side-panel">
        <div className="card">
          <h3 style={{ marginTop: 0 }}>קביעת מידות</h3>
          <label>ציר מוביל</label>
          <Select value={axis} onChange={(v) => setAxis(v as "x" | "y" | "z")}
                  options={[
                    { value: "z", label: "גובה (Z)" },
                    { value: "x", label: "רוחב (X)" },
                    { value: "y", label: "עומק (Y)" },
                  ]} />
          <label style={{ marginTop: "0.7rem" }}>מידה במ"מ</label>
          <input type="number" min={5} max={500} value={sizeMm}
                 onChange={(e) => setSizeMm(Number(e.target.value))} style={{ width: "100%" }} />
          <input type="range" min={10} max={300} value={sizeMm}
                 onChange={(e) => setSizeMm(Number(e.target.value))} style={{ width: "100%" }} />
          <label style={{ marginTop: "0.7rem" }}>מדפסת (לבדיקת נפח)</label>
          <Select value={profileId || job.profile_id || ""} onChange={setProfileId}
                  placeholder="— ללא —"
                  options={[
                    { value: "", label: "— ללא —" },
                    ...(profiles ?? []).map((p) => ({
                      value: p.id, label: p.name,
                      hint: `${p.bed_x}×${p.bed_y}×${p.bed_z}`,
                    })),
                  ]} />
          <label style={{ marginTop: "0.7rem" }}>סיבוב ידני (snap 15°)</label>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
            <RotationControl label="X" value={rot[0]} onChange={(v) => setRot([v, rot[1], rot[2]])} />
            <RotationControl label="Y" value={rot[1]} onChange={(v) => setRot([rot[0], v, rot[2]])} />
            <RotationControl label="Z" value={rot[2]} onChange={(v) => setRot([rot[0], rot[1], v])} />
          </div>
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
  const [profileId, setProfileId] = useState(job.profile_id || getDefaultProfileId());
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
          <h3 style={{ marginTop: 0 }}>הגדרות Slicing</h3>
          <label>מדפסת</label>
          <Select value={profileId} onChange={setProfileId} placeholder="בחר מדפסת…"
                  options={(profiles ?? []).map((p) => ({
                    value: p.id, label: p.name,
                    hint: `${p.bed_x}×${p.bed_y}×${p.bed_z}`,
                  }))} />
          <label style={{ marginTop: "0.7rem" }}>פריסט איכות</label>
          <Select value={preset} onChange={(v) => setPreset(v as typeof preset)}
                  options={[
                    { value: "draft", label: "Draft — מהיר", hint: "0.28mm" },
                    { value: "standard", label: "Standard", hint: "0.2mm" },
                    { value: "quality", label: "Quality — מדויק", hint: "0.12mm" },
                  ]} />
          <label style={{ marginTop: "0.7rem" }}>חומר</label>
          <Select value={material} onChange={(v) => setMaterial(v as typeof material)}
                  options={[
                    { value: "PLA", label: "PLA" },
                    { value: "PETG", label: "PETG" },
                    { value: "TPU", label: "TPU (גמיש)" },
                  ]} />

          <label style={{ marginTop: "0.9rem" }}>
            <input type="checkbox" checked={advanced} onChange={(e) => setAdvanced(e.target.checked)} /> מצב Advanced
          </label>
          {advanced && (
            <div style={{ background: "var(--bg)", borderRadius: 10, padding: "0.8rem", marginTop: "0.5rem" }}>
              <label>Infill: {adv.infill_pct}%</label>
              <input type="range" min={0} max={60} value={adv.infill_pct}
                     onChange={(e) => setAdv({ ...adv, infill_pct: Number(e.target.value) })} style={{ width: "100%" }} />
              <label style={{ marginTop: "0.5rem" }}>Supports</label>
              <Select value={adv.supports} onChange={(v) => setAdv({ ...adv, supports: v })}
                      options={[
                        { value: "auto", label: "אוטומטי" },
                        { value: "tree", label: "Tree (אורגני)" },
                        { value: "off", label: "כבוי" },
                      ]} />
              <label style={{ marginTop: "0.5rem" }}>
                <input type="checkbox" checked={adv.brim} onChange={(e) => setAdv({ ...adv, brim: e.target.checked })} /> Brim (הצמדות)
              </label>
            </div>
          )}

          <button style={{ width: "100%", marginTop: "1rem" }}
                  disabled={!profileId || slice.isPending}
                  onClick={() => slice.mutate()}>
            {slice.isPending ? "פורס…" : "הרץ Slicing"}
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
  const { data: profiles } = useQuery({ queryKey: ["profiles"], queryFn: api.listProfiles });
  const profile = profiles?.find((p) => p.id === job.profile_id);
  const [showSlice, setShowSlice] = useState(false);
  const [lightbox, setLightbox] = useState<string | null>(null);
  const qc = useQueryClient();

  // מיפוי החלפות צבע (שכבה) → גובה Z לצביעת המודל התלת-ממדי
  const { data: layersData } = useQuery({
    queryKey: ["gcode_layers", job.id],
    queryFn: () => api.gcodeLayers(job.id),
    enabled: !!stats?.color_changes?.length,
    staleTime: Infinity,
  });
  const colorZones = useMemo(() => {
    const ls = layersData?.layers;
    const cc = stats?.color_changes;
    if (!ls?.length || !cc?.length) return undefined;
    return cc.map((c) => ({
      z: ls[Math.min(Math.max(c.layer - 1, 0), ls.length - 1)].z,
      color: c.color,
    }));
  }, [layersData, stats?.color_changes]);

  // slice מחדש עם החלפות צבע (M600) — שומר את שאר הפרמטרים מהריצה האחרונה
  const applyColors = useMutation({
    mutationFn: (changes: { layer: number; color: string }[]) => {
      const prev = (job.slice_json ?? {}) as Record<string, unknown>;
      const advanced = { ...((prev.advanced as object) ?? {}), color_changes: changes };
      return api.slice(job.id, { ...prev, advanced });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["job", job.id] });
      qc.invalidateQueries({ queryKey: ["gcode_layers", job.id] });
    },
  });

  const t = stats?.time_s ?? 0;
  const timeStr = t >= 3600 ? `${Math.floor(t / 3600)}:${String(Math.floor((t % 3600) / 60)).padStart(2, "0")} שע'` : `${Math.round(t / 60)} דק'`;

  return (
    <>
      <div className="stat-strip">
        <div><b>{timeStr}</b><span>זמן הדפסה</span></div>
        <div><b>{stats?.filament_g?.toFixed(0) ?? "?"} גרם</b><span>חוט</span></div>
        <div><b>₪{stats?.cost?.total_ils ?? "?"}</b><span>עלות משוערת</span></div>
        <div><b>{stats?.layers ?? "?"}</b><span>שכבות</span></div>
        <div><b>{stats?.profile ?? "?"}</b><span>מדפסת</span></div>
      </div>

      {stats?.parts && stats.parts.length > 1 && (
        <div className="card" style={{ margin: "1rem 0" }}>
          <b>המודל חולק ל-{stats.parts.length} חלקים</b> — כל חלק מודפס בנפרד ומודבק בסיום.
          <table className="jobs" style={{ marginTop: "0.5rem" }}>
            <thead><tr><th>קובץ</th><th>זמן</th><th>חוט</th><th>שכבות</th><th></th></tr></thead>
            <tbody>
              {stats.parts.map((p) => {
                const art = job.artifacts.filter((a) => a.kind === "gcode" && a.filename === p.file).pop();
                return (
                  <tr key={p.file}>
                    <td className="mono" style={{ fontSize: "0.8rem" }}>{p.file}</td>
                    <td>{Math.round(p.time_s / 60)} דק'</td>
                    <td>{p.filament_g} גרם</td>
                    <td>{p.layers}</td>
                    <td>{art && <a className="btn secondary" style={{ padding: "0.2rem 0.7rem", fontSize: "0.82rem" }} href={api.artifactUrl(art.id)}>הורדה</a>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="row" style={{ margin: "1rem 0" }}>
        <a className="btn" href={api.downloadUrl(job.id)}>הורדת חבילה מלאה (ZIP)</a>
        {gcode && !stats?.parts && <a className="btn secondary" href={api.artifactUrl(gcode.id)}>G-code</a>}
        {mesh && <a className="btn secondary" href={api.artifactUrl(mesh.id)}>STL</a>}
        {report && <a className="btn secondary" href={api.artifactUrl(report.id)} target="_blank">דוח מלא</a>}
        <button className="secondary" onClick={() => setShowSlice(true)}>Slicing עם פרופיל אחר</button>
      </div>

      {showSlice && <SliceView job={job} />}

      <div className="split-eq">
        <div>
          <h2>Preview שכבות{stats?.color_changes?.length ? " · רב-צבעי" : ""}</h2>
          <GcodePreview jobId={job.id}
                        bed={profile ? { x: profile.bed_x, y: profile.bed_y } : undefined}
                        colorChanges={stats?.color_changes ?? []}
                        onApplyColorChanges={(c) => applyColors.mutate(c)} />
        </div>
        {previews.length > 0 && (
          <div>
            <h2>
              תצוגות מקדימות <span className="muted" style={{ fontSize: "0.8rem", fontWeight: 400 }}>· תמונות שטוחות, לחיצה מגדילה</span>
              {mesh && (
                <>
                  {" · "}
                  <a href="#viewer-3d" style={{ fontSize: "0.8rem", fontWeight: 400 }}
                     onClick={(e) => {
                       e.preventDefault();
                       document.getElementById("viewer-3d")?.scrollIntoView({ behavior: "smooth", block: "start" });
                     }}>
                    צפייה תלת-ממדית אינטראקטיבית ↓
                  </a>
                </>
              )}
            </h2>
            <div className="thumbs">
              {previews.map((p) => (
                <img key={p.id} src={api.artifactUrl(p.id)} alt={p.filename}
                     loading="lazy"
                     onClick={() => setLightbox(api.artifactUrl(p.id))} />
              ))}
            </div>
          </div>
        )}
      </div>
      {lightbox && <Lightbox src={lightbox} onClose={() => setLightbox(null)} />}

      {mesh && (
        <div id="viewer-3d" style={{ scrollMarginTop: "1.5rem" }}>
          <h2>המודל הסופי{stats?.color_changes?.length ? " · צבוע לפי ההחלפות" : ""}
            {" "}<span className="muted" style={{ fontSize: "0.8rem", fontWeight: 400 }}>· גררו לסיבוב, גלגלת לזום אמיתי על הגיאומטריה</span>
          </h2>
          <Viewer3D stlUrl={api.artifactUrl(mesh.id)} colorZones={colorZones} />
        </div>
      )}
    </>
  );
}
