// S-1 — דף בית / העלאה: גרירה, טאבים, "נוצרו לאחרונה"
import { useCallback, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, getDefaultProfileId, thumbnailArtifact } from "../api";

type Tab = "image" | "multi" | "mesh";

const ACCEPT: Record<Tab, string> = {
  image: ".jpg,.jpeg,.png,.webp,.heic",
  multi: ".jpg,.jpeg,.png,.webp,.heic",
  mesh: ".stl,.obj,.3mf,.ply,.glb",
};

export default function UploadPage() {
  const [tab, setTab] = useState<Tab>("image");
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const nav = useNavigate();

  const { data: jobs } = useQuery({ queryKey: ["jobs"], queryFn: api.listJobs });

  const create = useMutation({
    mutationFn: (files: File[]) => api.createJob(files, getDefaultProfileId() || undefined),
    onSuccess: (job) => nav(`/jobs/${job.id}`),
  });

  const onFiles = useCallback((list: FileList | null) => {
    if (!list?.length) return;
    create.mutate(Array.from(list));
  }, [create]);

  const recent = (jobs ?? []).slice(0, 6);

  return (
    <>
      <h1>מתמונה אחת — לחבילת הדפסה מלאה</h1>
      <p className="muted">
        העלה תמונה של חפץ (או קובץ תלת-ממד קיים) וקבל STL מתוקן, G-code מוכן למדפסת,
        דוח עלויות ותצוגה תלת-ממדית — עם שערי איכות בכל שלב.
      </p>

      <div className="tabs">
        <button className={tab === "image" ? "active" : ""} onClick={() => setTab("image")}>תמונה בודדת</button>
        <button className={tab === "multi" ? "active" : ""} onClick={() => setTab("multi")} title="פוטוגרמטריה — בקרוב (v1.5)">ריבוי תמונות</button>
        <button className={tab === "mesh" ? "active" : ""} onClick={() => setTab("mesh")}>קובץ 3D קיים</button>
      </div>

      <div className="split-2">
        <div>
          {tab === "multi" ? (
            <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
              <p>מסלול פוטוגרמטריה (20–50 תמונות מזוויות שונות) יגיע בגרסה 1.5 עם Meshroom.</p>
            </div>
          ) : (
            <div
              className={`dropzone ${drag ? "drag" : ""}`}
              onClick={() => inputRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => { e.preventDefault(); setDrag(false); onFiles(e.dataTransfer.files); }}
            >
              <div className="big">+</div>
              <h3>{create.isPending ? "מעלה…" : "גרור לכאן או לחץ לבחירה"}</h3>
              <p className="muted">
                {tab === "image"
                  ? "JPG / PNG / WEBP / HEIC · עד 20MB · מינימום 512×512"
                  : "STL / OBJ / 3MF / PLY / GLB · עד 200MB"}
              </p>
              <input ref={inputRef} type="file" hidden accept={ACCEPT[tab]}
                     onChange={(e) => onFiles(e.target.files)} />
            </div>
          )}
          {create.isError && (
            <div className="error-box">שגיאה: {(create.error as Error).message}</div>
          )}
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>טיפים לצילום מוצלח</h3>
          <ul className="muted" style={{ lineHeight: 1.9 }}>
            <li>אור טבעי חזק ואחיד, בלי צללים קשים</li>
            <li>רקע חלק בצבע מנוגד לחפץ</li>
            <li>החפץ ממלא את רוב הפריים, במוקד חד</li>
            <li>זווית של ~30° מעל קו האופק מציגה הכי הרבה גיאומטריה</li>
          </ul>
        </div>
      </div>

      {recent.length > 0 && (
        <>
          <h2>נוצרו לאחרונה</h2>
          <div className="gallery">
            {recent.map((j) => {
              const preview = thumbnailArtifact(j);
              const badge = j.status === "done" ? "done" : j.status === "failed" ? "failed"
                : j.status.startsWith("awaiting") ? "waiting" : "working";
              const badgeText: Record<string, string> = {
                done: "הושלם", failed: "נכשל", waiting: "ממתין לך", working: "מעבד",
              };
              return (
                <Link key={j.id} to={`/jobs/${j.id}`} className="gallery-card">
                  <div className="gallery-thumb">
                    {preview
                      ? <img src={api.artifactUrl(preview.id)} alt="" loading="lazy" />
                      : <span className="muted" style={{ fontSize: "0.8rem", letterSpacing: "0.08em" }}>
                          {j.input_type === "mesh" ? "3D" : "IMG"}
                        </span>}
                  </div>
                  <div className="gallery-meta">
                    <span className="mono">{j.id}</span>
                    <span className={`badge ${badge}`}>{badgeText[badge]}</span>
                  </div>
                </Link>
              );
            })}
          </div>
        </>
      )}
    </>
  );
}
