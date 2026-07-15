// שורת שערי איכות — שישה צ'יפים עם tooltip (S-4)
import type { Gate } from "../api";

const GATE_LABELS: Record<string, string> = {
  QG1: "התאמת תמונה",
  QG2: "ביטחון AI",
  QG3: "אטימות",
  QG4: "עובי דופן",
  QG5: "נפח הדפסה",
  QG6: "תקינות G-code",
};

export default function GatesRow({ gates }: { gates: Record<string, Gate> }) {
  const all = ["QG1", "QG2", "QG3", "QG4", "QG5", "QG6"];
  return (
    <div className="gates-row">
      {all.map((g) => {
        const info = gates[g];
        const status = info?.status ?? "pending";
        return (
          <span key={g} className={`gate-chip ${status}`}
                title={info?.message_he || "טרם נבדק"}>
            {GATE_LABELS[g]}
          </span>
        );
      })}
    </div>
  );
}
