// חיבור WebSocket לעדכוני התקדמות + ריענון הג'וב בכל שינוי סטטוס
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { ProgressEvent } from "../api";

export function useJobProgress(jobId: string | undefined) {
  const [event, setEvent] = useState<ProgressEvent | null>(null);
  const qc = useQueryClient();

  useEffect(() => {
    if (!jobId) return;
    let ws: WebSocket | null = null;
    let closed = false;
    let lastStatus = "";

    function connect() {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws/jobs/${jobId}`);
      ws.onmessage = (msg) => {
        const data: ProgressEvent = JSON.parse(msg.data);
        if (data.type === "keepalive") return;
        setEvent(data);
        if (data.status !== lastStatus) {
          lastStatus = data.status;
          qc.invalidateQueries({ queryKey: ["job", jobId] });
        }
      };
      ws.onclose = () => {
        if (!closed) setTimeout(connect, 2000); // reconnect
      };
    }
    connect();
    return () => { closed = true; ws?.close(); };
  }, [jobId, qc]);

  return event;
}
