import { publicPost } from "./api";

let memoryVisitId: string | null = null;
const VISIT_KEY = "sim2policy.analytics.visit";

function mintVisitId(): string {
  return crypto.randomUUID();
}

function visitId(): string {
  try {
    const existing = sessionStorage.getItem(VISIT_KEY);
    if (existing) return existing;
    const created = mintVisitId();
    sessionStorage.setItem(VISIT_KEY, created);
    return created;
  } catch {
    memoryVisitId ??= mintVisitId();
    return memoryVisitId;
  }
}

/** Record one SPA view without ever affecting rendering or navigation. */
export function trackView(view: string, entityId?: string): void {
  void publicPost(
    "/analytics/collect",
    { visit_id: visitId(), view, entity_id: entityId },
    { keepalive: true },
  ).catch(() => {});
}
