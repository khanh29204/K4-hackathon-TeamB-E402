import { apiGet, apiPost } from "./client.js";

export const CONNECTIONS_KEY = "/connections";

export async function getConnections() {
  return apiGet(CONNECTIONS_KEY);
}

// Progress of the background mail/Discord sync a connect triggers (see
// backend studypulse/ingest_status.py) — e.g. { gmail: { status: "running" } }.
export async function getIngestStatus() {
  return apiGet(`${CONNECTIONS_KEY}/ingest-status`);
}

export async function getGoogleAuthUrl() {
  const data = await apiGet("/connections/google/start");
  return data.auth_url;
}

export async function disconnectGoogle() {
  return apiPost("/connections/google/disconnect");
}

export async function getDiscordInviteUrl() {
  const data = await apiGet("/connections/discord/start");
  return data.invite_url;
}

export async function disconnectDiscord(guildId) {
  return apiPost("/connections/discord/disconnect", { guild_id: guildId });
}

export async function startOutlookConnect() {
  return apiPost("/connections/outlook/start");
}

export async function getOutlookConnectStatus() {
  return apiGet("/connections/outlook/connect-status");
}

export async function disconnectOutlook() {
  return apiPost("/connections/outlook/disconnect");
}
