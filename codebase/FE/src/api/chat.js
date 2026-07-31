import { ApiError, apiPost } from "./client.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

export async function sendChatMessage({ conversationId, userQuery }) {
  return apiPost("/chat", { conversation_id: conversationId, user_query: userQuery });
}

export async function sendChatMessageStream({ conversationId, userQuery, onDelta, onStatus, onDone, onError }) {
  const response = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_id: conversationId, user_query: userQuery }),
  });

  if (!response.ok) {
    let errorMsg = "Đã xảy ra lỗi khi kết nối với máy chủ.";
    try {
      const errJson = await response.json();
      if (errJson.detail?.error?.message) errorMsg = errJson.detail.error.message;
      else if (errJson.error?.message) errorMsg = errJson.error.message;
    } catch {}
    throw new ApiError("HTTP_ERROR", errorMsg);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\n\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data: ")) continue;
      const dataStr = trimmed.slice(6);
      try {
        const payload = JSON.parse(dataStr);
        if (payload.type === "status" && onStatus) {
          onStatus(payload.message);
        } else if (payload.type === "delta" && onDelta) {
          onDelta(payload.text);
        } else if (payload.type === "done" && onDone) {
          onDone(payload.data);
        } else if (payload.type === "error" && onError) {
          onError(payload.message);
        }
      } catch (e) {
        console.error("Failed to parse SSE payload:", e);
      }
    }
  }
}
