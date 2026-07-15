// שכבת API — טיפוסים וקריאות לשרת

export interface Gate {
  status: "pass" | "warn" | "fail" | "pending";
  message_he: string;
  [k: string]: unknown;
}

export interface Stage {
  stage_name: string;
  stage_index: number;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  metrics_json: Record<string, unknown>;
  error_json: Record<string, unknown> | null;
}

export interface Artifact {
  id: string;
  kind: string;
  filename: string;
  size_bytes: number;
  sha256: string;
}

export interface Job {
  id: string;
  status: string;
  input_type: string;
  source_provider: string | null;
  image_score: number | null;
  ai_confidence: number | null;
  error_he: string | null;
  gates_json: Record<string, Gate>;
  scale_json: Record<string, unknown> | null;
  slice_json: Record<string, unknown> | null;
  print_stats_json: PrintStats | null;
  profile_id: string | null;
  created_at: string;
  stages: Stage[];
  artifacts: Artifact[];
}

export interface PartStat {
  file: string;
  time_s: number;
  filament_g: number;
  layers: number;
}

export interface PrintStats {
  time_s: number;
  filament_mm: number;
  filament_g: number;
  layers: number;
  cost?: { filament_ils: number; electricity_ils: number; total_ils: number };
  profile?: string;
  preset?: string;
  material?: string;
  parts?: PartStat[] | null;
  color_changes?: { layer: number; color: string }[] | null;
  [k: string]: unknown;
}

export interface Profile {
  id: string;
  name: string;
  vendor: string;
  bed_x: number;
  bed_y: number;
  bed_z: number;
  nozzle_mm: number;
  is_builtin: boolean;
}

export interface ProgressEvent {
  job_id: string;
  status: string;
  stage: string;
  stage_index: number;
  total_stages: number;
  progress_pct: number;
  message_he: string;
  gates: Record<string, string>;
  error?: { gate?: string; message_he: string; suggestions_he?: string[] };
  type?: string;
}

async function check(res: Response) {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch { /* body לא JSON */ }
    throw new Error(detail);
  }
  return res;
}

export const api = {
  async createJob(files: File[], profileId?: string): Promise<Job> {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    if (profileId) fd.append("profile_id", profileId);
    return (await check(await fetch("/api/v1/jobs", { method: "POST", body: fd }))).json();
  },
  async getJob(id: string): Promise<Job> {
    return (await check(await fetch(`/api/v1/jobs/${id}`))).json();
  },
  async listJobs(): Promise<Job[]> {
    return (await check(await fetch("/api/v1/jobs"))).json();
  },
  async scale(id: string, body: object): Promise<Job> {
    return (await check(await fetch(`/api/v1/jobs/${id}/scale`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }))).json();
  },
  async slice(id: string, body: object): Promise<Job> {
    return (await check(await fetch(`/api/v1/jobs/${id}/slice`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }))).json();
  },
  async duplicate(id: string): Promise<Job> {
    return (await check(await fetch(`/api/v1/jobs/${id}/duplicate`, { method: "POST" }))).json();
  },
  async deleteJob(id: string): Promise<void> {
    await check(await fetch(`/api/v1/jobs/${id}`, { method: "DELETE" }));
  },
  async listProfiles(): Promise<Profile[]> {
    return (await check(await fetch("/api/v1/profiles"))).json();
  },
  async gcodeLayers(jobId: string): Promise<{ layers: { z: number; segments: number[][] }[]; count: number }> {
    return (await check(await fetch(`/api/v1/jobs/${jobId}/gcode_layers`))).json();
  },
  artifactUrl(id: string): string {
    return `/api/v1/artifacts/${id}`;
  },
  downloadUrl(jobId: string): string {
    return `/api/v1/jobs/${jobId}/download`;
  },
};

export function latestArtifact(job: Job, kind: string): Artifact | undefined {
  return [...job.artifacts].reverse().find((a) => a.kind === kind);
}

// מדפסת ברירת מחדל — נשמרת מקומית ומוזרקת לכל ג'וב חדש
const DEFAULT_PROFILE_KEY = "p2p_default_profile";

export function getDefaultProfileId(): string {
  return localStorage.getItem(DEFAULT_PROFILE_KEY) ?? "";
}

export function setDefaultProfileId(id: string) {
  if (id) localStorage.setItem(DEFAULT_PROFILE_KEY, id);
  else localStorage.removeItem(DEFAULT_PROFILE_KEY);
}

export function thumbnailArtifact(job: Job): Artifact | undefined {
  // תמונה ממוזערת עקבית: hero איזומטרי > front > כל preview סטטי אחר (לא GIF)
  const previews = job.artifacts.filter((a) => a.kind === "preview");
  return (
    previews.find((a) => a.filename.includes("iso")) ??
    previews.find((a) => a.filename.includes("front")) ??
    previews.find((a) => a.filename.endsWith(".png"))
  );
}
