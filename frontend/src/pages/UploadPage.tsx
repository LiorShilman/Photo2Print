// S-1 — דף בית / העלאה: גרירה, טאבים, "נוצרו לאחרונה"
import { useCallback, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, getDefaultProfileId, thumbnailArtifact, type LithophaneOptions } from "../api";
import { IconCube, IconImage, IconUpload } from "../components/icons";
import Select from "../components/Select";

type Tab = "image" | "multi" | "mesh" | "litho" | "text";

const ACCEPT: Record<Tab, string> = {
  image: ".jpg,.jpeg,.png,.webp,.heic",
  multi: ".jpg,.jpeg,.png,.webp,.heic",
  mesh: ".stl,.obj,.3mf,.ply,.glb",
  litho: ".jpg,.jpeg,.png,.webp,.heic",
  text: "",
};

export default function UploadPage() {
  const [tab, setTab] = useState<Tab>("image");
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const nav = useNavigate();

  const [litho, setLitho] = useState<LithophaneOptions>({
    shape: "flat", invert: false, wrap_deg: 200, min_thickness_mm: 0.8, max_thickness_mm: 3.2,
  });
  const [prompt, setPrompt] = useState("");

  const { data: jobs } = useQuery({ queryKey: ["jobs"], queryFn: api.listJobs });

  const create = useMutation({
    mutationFn: (files: File[]) =>
      api.createJob(files, getDefaultProfileId() || undefined, tab === "litho" ? litho : undefined),
    onSuccess: (job) => nav(`/jobs/${job.id}`),
  });

  const createFromText = useMutation({
    mutationFn: () => api.createJobFromText(prompt.trim(), getDefaultProfileId() || undefined),
    onSuccess: (job) => nav(`/jobs/${job.id}`),
  });

  const onFiles = useCallback((list: FileList | null) => {
    if (!list?.length) return;
    create.mutate(Array.from(list));
  }, [create, tab, litho]);

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
        <button className={tab === "litho" ? "active" : ""} onClick={() => setTab("litho")}>ליתופן</button>
        <button className={tab === "text" ? "active" : ""} onClick={() => setTab("text")}>תיאור טקסטואלי</button>
      </div>

      <div className="split-2">
        <div>
          {tab === "multi" ? (
            <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
              <p>מסלול פוטוגרמטריה (20–50 תמונות מזוויות שונות) יגיע בגרסה 1.5 עם Meshroom.</p>
            </div>
          ) : tab === "text" ? (
            <div className="card">
              <label>תיאור החפץ שברצונך להדפיס (באנגלית)</label>
              <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={6}
                        placeholder="Example: a small sitting cartoon dragon figurine, flat base"
                        style={{ width: "100%", resize: "vertical" }} />
              <button style={{ marginTop: "0.8rem" }} disabled={prompt.trim().length < 3 || createFromText.isPending}
                      onClick={() => createFromText.mutate()}>
                {createFromText.isPending ? "יוצר…" : "צור מודל"}
              </button>
              {createFromText.isError && (
                <div className="error-box" style={{ marginTop: "0.8rem" }}>
                  שגיאה: {(createFromText.error as Error).message}
                </div>
              )}
            </div>
          ) : (
            <div
              className={`dropzone ${drag ? "drag" : ""}`}
              onClick={() => inputRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => { e.preventDefault(); setDrag(false); onFiles(e.dataTransfer.files); }}
            >
              <div className="big" style={{ color: "#a5b4fc" }}>
                <IconUpload size={30} />
              </div>
              <h3>{create.isPending ? "מעלה…" : "גרור לכאן או לחץ לבחירה"}</h3>
              <p className="muted">
                {tab === "mesh"
                  ? "STL / OBJ / 3MF / PLY / GLB · עד 200MB"
                  : "JPG / PNG / WEBP / HEIC · עד 20MB · מינימום 512×512"}
              </p>
              <input ref={inputRef} type="file" hidden accept={ACCEPT[tab]}
                     onChange={(e) => onFiles(e.target.files)} />
            </div>
          )}
          {create.isError && (
            <div className="error-box">שגיאה: {(create.error as Error).message}</div>
          )}
        </div>

        {tab === "litho" ? (
          <div className="card">
            <h3 style={{ marginTop: 0 }}>אפשרויות ליתופן</h3>
            <label>צורה</label>
            <Select value={litho.shape} onChange={(v) => setLitho({ ...litho, shape: v as "flat" | "cylindrical" })}
                    options={[
                      { value: "flat", label: "פאנל שטוח" },
                      { value: "cylindrical", label: "עקום / גלילי (שקף מנורה)" },
                    ]} />
            {litho.shape === "cylindrical" && (
              <>
                <label style={{ marginTop: "0.7rem" }}>זווית עטיפה: {litho.wrap_deg}°</label>
                <input type="range" min={30} max={340} value={litho.wrap_deg}
                       onChange={(e) => setLitho({ ...litho, wrap_deg: Number(e.target.value) })}
                       style={{ width: "100%" }} />
              </>
            )}
            <label style={{ marginTop: "0.7rem" }}>
              <input type="checkbox" checked={litho.invert}
                     onChange={(e) => setLitho({ ...litho, invert: e.target.checked })} />
              {" "}הפוך עובי (כהה=דק / בהיר=עבה)
            </label>
            <p className="muted" style={{ fontSize: "0.85rem", marginTop: "0.7rem" }}>
              עובי {litho.min_thickness_mm}–{litho.max_thickness_mm} מ"מ (מתכוונן יחסית לגודל הסופי בשלב הסקייל).
            </p>
          </div>
        ) : tab === "text" ? (
          <div className="card">
            <h3 style={{ marginTop: 0 }}>טיפים לתיאור טוב</h3>
            <ul className="muted" style={{ lineHeight: 1.9 }}>
              <li><b>כתבו את התיאור באנגלית</b> — במיוחד עם shap_e המקומי, שמבוסס על CLIP ואינו מבין עברית באמת</li>
              <li>תארו חפץ בודד וברור, לא סצנה שלמה</li>
              <li>ציינו סגנון (ריאליסטי / קריקטורי / low-poly)</li>
              <li>אם חשוב בסיס שטוח להדפסה — ציינו זאת מפורשות</li>
              <li>דורש ספק שתומך בטקסט: Tripo3D/Meshy (מפתח API בענן) או shap_e (מקומי וללא מפתח, אך איטי ודורש התקנה נפרדת — ראה README)</li>
            </ul>
          </div>
        ) : (
          <div className="card">
            <h3 style={{ marginTop: 0 }}>טיפים לצילום מוצלח</h3>
            <ul className="muted" style={{ lineHeight: 1.9 }}>
              <li>אור טבעי חזק ואחיד, בלי צללים קשים</li>
              <li>רקע חלק בצבע מנוגד לחפץ</li>
              <li>החפץ ממלא את רוב הפריים, במוקד חד</li>
              <li>זווית של ~30° מעל קו האופק מציגה הכי הרבה גיאומטריה</li>
            </ul>
          </div>
        )}
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
                      : <span style={{ color: "#4a5170" }}>
                          {j.input_type === "mesh" ? <IconCube size={34} /> : <IconImage size={34} />}
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
