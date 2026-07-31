import { apiGet, apiPost } from "./client.js";

export const HITL_KEY = "/hitl";

// Items paused at hitl_escalation — low-confidence or conflicting
// extractions the graph won't auto-add to the timeline (see backend
// studypulse/hitl.py). Never reaches the timeline until reviewed here.
export async function getHitlItems() {
  const data = await apiGet(HITL_KEY);
  return data.items;
}

export async function approveHitlItem(threadId, itemId, edits) {
  return apiPost(`/hitl/${threadId}/${itemId}/approve`, edits ? { edits } : {});
}

export async function rejectHitlItem(threadId, itemId) {
  return apiPost(`/hitl/${threadId}/${itemId}/reject`, {});
}
