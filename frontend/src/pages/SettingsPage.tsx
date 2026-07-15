// S-7 — הגדרות: מדפסת ברירת מחדל, פרופילי מדפסות, מידע מערכת
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, getDefaultProfileId, setDefaultProfileId } from "../api";
import Select from "../components/Select";

export default function SettingsPage() {
  const qc = useQueryClient();
  const { data: profiles } = useQuery({ queryKey: ["profiles"], queryFn: api.listProfiles });
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: async () => (await fetch("/api/v1/health")).json(),
  });

  const [defaultProfile, setDefaultProfile] = useState(getDefaultProfileId());
  const [form, setForm] = useState({ name: "", bed_x: 220, bed_y: 220, bed_z: 250, nozzle_mm: 0.4 });
  const create = useMutation({
    mutationFn: async () => {
      const res = await fetch("/api/v1/profiles", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, slicer_ini_base: "generic_fdm.ini" }),
      });
      if (!res.ok) throw new Error((await res.json()).detail);
      return res.json();
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["profiles"] }); setForm({ ...form, name: "" }); },
  });

  return (
    <>
      <h1>הגדרות</h1>

      <h2>מצב מערכת</h2>
      <div className="card">
        <p>Slicer: {health?.slicer_found
          ? <span style={{ color: "var(--ok)" }}>✔ נמצא <span className="mono" style={{ fontSize: "0.8rem" }}>{health.slicer_path}</span></span>
          : <span style={{ color: "var(--error)" }}>✘ לא נמצא — בדוק את tools/ או P2P_SLICER_PATH</span>}</p>
        <p>ספק יצירת מודלים: <b className="mono">{health?.mesh_provider}</b>
          {health?.mesh_provider === "local_extrude" &&
            <span className="muted"> (אקסטרוזיית צללית — ל-AI מלא הגדר מפתח Tripo/Meshy ב-.env)</span>}
        </p>
      </div>

      <h2>המדפסת שלי</h2>
      <div className="card" style={{ maxWidth: 560 }}>
        <label>מדפסת ברירת מחדל — תיבחר אוטומטית בכל ג'וב חדש</label>
        <Select
          value={defaultProfile}
          onChange={(v) => { setDefaultProfile(v); setDefaultProfileId(v); }}
          placeholder="בחר מדפסת…"
          options={[
            { value: "", label: "— ללא (בחירה ידנית בכל ג'וב) —" },
            ...(profiles ?? []).map((p) => ({
              value: p.id, label: p.name, hint: `${p.bed_x}×${p.bed_y}×${p.bed_z}`,
            })),
          ]}
        />
      </div>

      <h2>פרופילי מדפסות</h2>
      <table className="jobs">
        <thead><tr><th>שם</th><th>יצרן</th><th>משטח (מ"מ)</th><th>נחיר</th><th></th></tr></thead>
        <tbody>
          {profiles?.map((p) => (
            <tr key={p.id}>
              <td>{p.name}</td>
              <td className="muted">{p.vendor}</td>
              <td className="mono">{p.bed_x}×{p.bed_y}×{p.bed_z}</td>
              <td className="mono">{p.nozzle_mm}</td>
              <td>{p.is_builtin ? <span className="muted">מובנה</span> :
                <button className="danger" style={{ padding: "0.2rem 0.6rem" }}
                        onClick={async () => { await fetch(`/api/v1/profiles/${p.id}`, { method: "DELETE" }); qc.invalidateQueries({ queryKey: ["profiles"] }); }}>🗑</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>הוספת פרופיל מותאם</h2>
      <div className="card">
        <div className="row">
          <div><label>שם</label><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
          <div><label>רוחב X</label><input type="number" value={form.bed_x} onChange={(e) => setForm({ ...form, bed_x: +e.target.value })} style={{ width: 90 }} /></div>
          <div><label>עומק Y</label><input type="number" value={form.bed_y} onChange={(e) => setForm({ ...form, bed_y: +e.target.value })} style={{ width: 90 }} /></div>
          <div><label>גובה Z</label><input type="number" value={form.bed_z} onChange={(e) => setForm({ ...form, bed_z: +e.target.value })} style={{ width: 90 }} /></div>
          <div><label>נחיר</label><input type="number" step={0.1} value={form.nozzle_mm} onChange={(e) => setForm({ ...form, nozzle_mm: +e.target.value })} style={{ width: 80 }} /></div>
          <button disabled={!form.name || create.isPending} onClick={() => create.mutate()} style={{ alignSelf: "flex-end" }}>הוסף</button>
        </div>
        {create.isError && <p style={{ color: "var(--error)" }}>{(create.error as Error).message}</p>}
      </div>
    </>
  );
}
