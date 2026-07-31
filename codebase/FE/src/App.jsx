import { useEffect, useState } from "react";
import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { initialMessages, initialPlatforms } from "./data.js";
import { ApiError } from "./api/client.js";
import { sendChatMessage, sendChatMessageStream } from "./api/chat.js";
import { TIMELINE_KEY, confirmCalendar, flagTimelineItem, getTimeline, patchTimelineItem } from "./api/timeline.js";
import {
  disconnectDiscord,
  disconnectGoogle,
  disconnectOutlook,
  getConnections,
  getDiscordInviteUrl,
  getGoogleAuthUrl,
  getOutlookConnectStatus,
  startOutlookConnect,
} from "./api/connections.js";
import { formatTime } from "./utils/formatters.js";
import { generateUUID } from "./utils/uuid.js";
import { parseOutlookDeviceCode } from "./utils/outlookDeviceCode.js";
import { QUICK_ACTION_QUERIES } from "./constants/chat.js";
import { Icon } from "./components/common/Icon.jsx";
import { Toast } from "./components/common/Toast.jsx";
import { Header } from "./components/layout/Header.jsx";
import { ChatPanel } from "./components/chat/ChatPanel.jsx";
import { Dashboard } from "./components/dashboard/Dashboard.jsx";
import { EditDialog } from "./components/dashboard/EditDialog.jsx";
import { OutlookDeviceCodeDialog } from "./components/dashboard/OutlookDeviceCodeDialog.jsx";

const SESSIONS_KEY = "studypulse_chat_sessions";
const GOOGLE_USER_CACHE_KEY = "studypulse_google_user";

export default function App() {
  const [sessions, setSessions] = useState(() => {
    try {
      const stored = localStorage.getItem(SESSIONS_KEY);
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  });

  const [conversationId, setConversationId] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    const urlC = params.get("c");
    if (urlC) return urlC;
    try {
      const stored = localStorage.getItem(SESSIONS_KEY);
      const parsed = stored ? JSON.parse(stored) : [];
      if (parsed.length > 0) return parsed[0].id;
    } catch {}
    return generateUUID();
  });

  const [messages, setMessages] = useState(() => {
    try {
      const stored = localStorage.getItem(SESSIONS_KEY);
      const parsed = stored ? JSON.parse(stored) : [];
      const match = parsed.find((s) => s.id === conversationId);
      if (match && match.messages?.length) return match.messages;
    } catch {}
    return initialMessages;
  });

  const [platforms, setPlatforms] = useState(initialPlatforms);
  const [activeAction, setActiveAction] = useState("week");
  const [showConnections, setShowConnections] = useState(false);
  const [editingEvent, setEditingEvent] = useState(null);
  const [toast, setToast] = useState(null);
  const [mobileView, setMobileView] = useState("dashboard");
  const [seededActions, setSeededActions] = useState(() => new Set());
  const [busyItemId, setBusyItemId] = useState(null);
  const [outlookConnecting, setOutlookConnecting] = useState(false);
  const [outlookDeviceCode, setOutlookDeviceCode] = useState(null);
  const [googleUser, setGoogleUser] = useState(() => {
    try {
      const cached = localStorage.getItem(GOOGLE_USER_CACHE_KEY);
      return cached ? JSON.parse(cached) : { connected: false, email: null };
    } catch {
      return { connected: false, email: null };
    }
  });

  // Keep URL search param ?c=<conversationId> in sync
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("c") !== conversationId) {
      params.set("c", conversationId);
      const newUrl = `${window.location.pathname}?${params.toString()}`;
      window.history.replaceState({}, "", newUrl);
    }
  }, [conversationId]);

  // Sync messages & session title back to localStorage
  useEffect(() => {
    if (!conversationId) return;
    setSessions((prevSessions) => {
      const firstUserMsg = messages.find((m) => m.role === "user");
      const title = firstUserMsg ? (firstUserMsg.text.length > 30 ? firstUserMsg.text.slice(0, 30) + "..." : firstUserMsg.text) : "Cuộc hội thoại mới";
      const now = new Date().toISOString();

      const existingIndex = prevSessions.findIndex((s) => s.id === conversationId);
      let updated;
      if (existingIndex >= 0) {
        updated = prevSessions.map((s) => (s.id === conversationId ? { ...s, title: firstUserMsg ? title : s.title, updatedAt: now, messages } : s));
      } else {
        updated = [{ id: conversationId, title, updatedAt: now, messages }, ...prevSessions];
      }
      try {
        localStorage.setItem(SESSIONS_KEY, JSON.stringify(updated));
      } catch {}
      return updated;
    });
  }, [conversationId, messages]);

  // Listen to popstate (browser back/forward button)
  useEffect(() => {
    const handlePopState = () => {
      const params = new URLSearchParams(window.location.search);
      const urlC = params.get("c");
      if (urlC && urlC !== conversationId) {
        setConversationId(urlC);
        try {
          const stored = localStorage.getItem(SESSIONS_KEY);
          const parsed = stored ? JSON.parse(stored) : [];
          const match = parsed.find((s) => s.id === urlC);
          setMessages(match?.messages || initialMessages);
        } catch {
          setMessages(initialMessages);
        }
      }
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [conversationId]);

  const switchConversation = (targetId) => {
    if (targetId === conversationId) return;
    setConversationId(targetId);
    const match = sessions.find((s) => s.id === targetId);
    setMessages(match?.messages || initialMessages);

    const params = new URLSearchParams(window.location.search);
    params.set("c", targetId);
    window.history.pushState({}, "", `${window.location.pathname}?${params.toString()}`);
  };

  const createNewConversation = () => {
    const newId = generateUUID();
    setConversationId(newId);
    setMessages(initialMessages);

    const params = new URLSearchParams(window.location.search);
    params.set("c", newId);
    window.history.pushState({}, "", `${window.location.pathname}?${params.toString()}`);
  };

  const deleteConversation = (targetId) => {
    const updated = sessions.filter((s) => s.id !== targetId);
    setSessions(updated);
    try {
      localStorage.setItem(SESSIONS_KEY, JSON.stringify(updated));
    } catch {}

    if (targetId === conversationId) {
      if (updated.length > 0) {
        switchConversation(updated[0].id);
      } else {
        createNewConversation();
      }
    }
  };

  const {
    data: events = [],
    error: timelineError,
    isLoading: timelineLoading,
    mutate: mutateTimeline,
  } = useSWR(TIMELINE_KEY, getTimeline);

  const { trigger: triggerChat, isMutating: isSending } = useSWRMutation("studypulse-chat", (_key, { arg }) => sendChatMessage(arg));

  const notify = (text, type = "success") => {
    setToast({ text, type });
    window.setTimeout(() => setToast(null), 2600);
  };

  const refreshConnections = async () => {
    try {
      const data = await getConnections();
      const freshGoogle = { connected: data.google.connected, email: data.google.email };
      setGoogleUser(freshGoogle);
      try {
        localStorage.setItem(GOOGLE_USER_CACHE_KEY, JSON.stringify(freshGoogle));
      } catch {}
      setPlatforms((current) =>
        current.map((platform) => {
          if (platform.id === "gmail") return { ...platform, connected: data.google.connected };
          if (platform.id === "discord") return { ...platform, connected: data.discord.connected, guilds: data.discord.guilds };
          if (platform.id === "outlook") return { ...platform, connected: data.outlook.connected };
          return platform;
        }),
      );
    } catch {
      // Backend may be offline; leave platforms as-is (mock state).
    }
  };

  // "pending"/"starting" mean the backend still has the sign-in container
  // open, waiting on the device-code login to finish — anything else is terminal.
  const applyOutlookConnectResult = (result) => {
    if (result.status === "connected") {
      setPlatforms((current) => current.map((platform) => (platform.id === "outlook" ? { ...platform, connected: true } : platform)));
      notify(result.message || "Outlook đã kết nối.", "success");
      setOutlookConnecting(false);
      setOutlookDeviceCode(null);
    } else if (result.status === "failed" || result.status === "timeout") {
      notify(result.message || "Kết nối Outlook thất bại, thử lại sau.", "error");
      setOutlookConnecting(false);
      setOutlookDeviceCode(null);
    } else if (result.status === "pending") {
      setOutlookConnecting(true);
      const parsed = parseOutlookDeviceCode(result.message);
      if (parsed) {
        setOutlookDeviceCode((current) => {
          if (current?.code === parsed.code) return current; // same code already shown/opened
          window.open(parsed.url, "_blank", "noopener,noreferrer");
          return parsed;
        });
      } else {
        notify(result.message || "Cần đăng nhập Outlook.", "info");
      }
    } else {
      setOutlookConnecting(true);
    }
  };

  const pollOutlookConnectStatus = async () => {
    for (;;) {
      await new Promise((resolve) => window.setTimeout(resolve, 4000));
      let result;
      try {
        result = await getOutlookConnectStatus();
      } catch {
        continue; // backend hiccup mid-poll — keep trying, don't give up the wait
      }
      applyOutlookConnectResult(result);
      if (result.status !== "pending" && result.status !== "starting") return;
    }
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const googleConnected = params.get("google_connected");
    if (googleConnected !== null) {
      notify(
        googleConnected === "1" ? "Đã kết nối Gmail & Google Calendar" : "Kết nối Gmail thất bại, thử lại sau.",
        googleConnected === "1" ? "success" : "error"
      );
      params.delete("google_connected");
      params.delete("reason");
      const query = params.toString();
      window.history.replaceState({}, "", window.location.pathname + (query ? `?${query}` : ""));
    }
    refreshConnections();
  }, []);

  useEffect(() => {
    // Re-check whenever the panel is opened — connecting Gmail (full-page
    // redirect) or Discord (opened in a new tab, no callback to us) both
    // happen outside this app, so the one-time fetch on initial load goes
    // stale as soon as either completes.
    if (showConnections) refreshConnections();
  }, [showConnections]);

  const sendMessage = async (text) => {
    if (!googleUser.connected) {
      notify("Vui lòng đăng nhập Google trước khi trò chuyện với AI.", "error");
      return;
    }
    const userMessageId = generateUUID();
    const loadingMessageId = generateUUID();
    setMessages((current) => [
      ...current,
      { id: userMessageId, role: "user", text, time: formatTime() },
      { id: loadingMessageId, role: "assistant", text: "", time: "", loading: true },
    ]);

    try {
      await sendChatMessageStream({
        conversationId,
        userQuery: text,
        onDelta: (chunk) => {
          setMessages((current) =>
            current.map((msg) =>
              msg.id === loadingMessageId
                ? {
                    ...msg,
                    loading: false,
                    text: msg.text + chunk,
                  }
                : msg,
            ),
          );
        },
        onStatus: (statusText) => {
          setMessages((current) =>
            current.map((msg) =>
              msg.id === loadingMessageId && !msg.text
                ? { ...msg, statusText }
                : msg,
            ),
          );
        },
        onDone: (data) => {
          setMessages((current) =>
            current.map((msg) =>
              msg.id === loadingMessageId
                ? {
                    ...msg,
                    loading: false,
                    text: data.response_text || msg.text,
                    time: formatTime(),
                    needsClarification: data.requires_clarification,
                    calendarEvents: data.calendar_events,
                  }
                : msg,
            ),
          );
          if (data.timeline_items_referenced?.length) {
            mutateTimeline();
          }
        },
        onError: (errMessage) => {
          setMessages((current) =>
            current.map((existing) =>
              existing.id === loadingMessageId
                ? {
                    id: loadingMessageId,
                    role: "assistant",
                    text: `${errMessage} Kiểm tra backend đã chạy chưa rồi thử lại.`,
                    time: formatTime(),
                    isError: true,
                    retryText: text,
                  }
                : existing,
            ),
          );
        },
      });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Không thể kết nối tới StudyPulse.";
      setMessages((current) =>
        current.map((existing) =>
          existing.id === loadingMessageId
            ? {
                id: loadingMessageId,
                role: "assistant",
                text: `${message} Kiểm tra backend đã chạy chưa rồi thử lại.`,
                time: formatTime(),
                isError: true,
                retryText: text,
              }
            : existing,
        ),
      );
    }
  };

  const handleAction = (id) => {
    setActiveAction(id);
    setShowConnections(false);
    if (!seededActions.has(id) && QUICK_ACTION_QUERIES[id]) {
      setSeededActions((current) => new Set(current).add(id));
      sendMessage(QUICK_ACTION_QUERIES[id]);
    }
  };

  const togglePlatform = async (id) => {
    if (id === "gmail") {
      const gmail = platforms.find((platform) => platform.id === "gmail");
      if (gmail?.connected) {
        const confirmed = window.confirm(
          "Hủy kết nối Gmail & Google Calendar?\n\nStudyPulse sẽ không thể đọc email hoặc lịch của bạn cho đến khi bạn kết nối lại.",
        );
        if (!confirmed) return;
        try {
          await disconnectGoogle();
          setPlatforms((current) => current.map((platform) => (platform.id === "gmail" ? { ...platform, connected: false } : platform)));
          notify("Đã hủy kết nối Gmail & Google Calendar", "info");
        } catch (err) {
          notify(err instanceof ApiError ? err.message : "Không thể hủy kết nối, thử lại sau.", "error");
        }
        return;
      }
      try {
        const authUrl = await getGoogleAuthUrl();
        window.location.href = authUrl;
      } catch (err) {
        notify(err instanceof ApiError ? err.message : "Không thể bắt đầu kết nối Gmail, kiểm tra backend.", "error");
      }
      return;
    }

    if (id === "outlook") {
      const outlook = platforms.find((platform) => platform.id === "outlook");
      if (outlook?.connected) {
        const confirmed = window.confirm(
          "Hủy kết nối Outlook?\n\nStudyPulse sẽ không thể đọc email hoặc lịch Outlook của bạn cho đến khi bạn kết nối lại.",
        );
        if (!confirmed) return;
        try {
          await disconnectOutlook();
          setPlatforms((current) => current.map((platform) => (platform.id === "outlook" ? { ...platform, connected: false } : platform)));
          notify("Đã hủy kết nối Outlook", "info");
        } catch (err) {
          notify(err instanceof ApiError ? err.message : "Không thể hủy kết nối, thử lại sau.", "error");
        }
        return;
      }

      // No browser-redirect OAuth here — outlook-local-mcp's Docker container
      // owns its own device-code sign-in. Clicking this actually triggers
      // that sign-in (backend keeps one container open across the wait, see
      // outlook_connection.py) rather than just checking a cached status.
      setOutlookConnecting(true);
      try {
        const initial = await startOutlookConnect();
        applyOutlookConnectResult(initial);
        if (initial.status === "pending" || initial.status === "starting") {
          await pollOutlookConnectStatus();
        }
      } catch (err) {
        notify(err instanceof ApiError ? err.message : "Không thể bắt đầu đăng nhập Outlook, kiểm tra backend.", "error");
        setOutlookConnecting(false);
      }
      return;
    }

    if (id === "discord") {
      // Bots can be in several servers at once, so the row's main button
      // always opens the invite flow (to add another one) — disconnecting a
      // specific server happens per-row in the guild list below, not here.
      try {
        const inviteUrl = await getDiscordInviteUrl();
        window.open(inviteUrl, "_blank", "noopener,noreferrer");
        notify("Cần quản trị viên server đồng ý mời bot. Sau khi mời xong, mở lại Quản lý kết nối để kiểm tra.", "info");
      } catch (err) {
        notify(err instanceof ApiError ? err.message : "Không thể lấy link mời bot, kiểm tra backend.", "error");
      }
      return;
    }

    setPlatforms((current) => current.map((platform) => (platform.id === id ? { ...platform, connected: true } : platform)));
    notify("Đã kết nối nền tảng thành công", "success");
  };

  const disconnectDiscordGuild = async (guildId, guildName) => {
    const confirmed = window.confirm(
      `Hủy kết nối server Discord "${guildName}"?\n\nBot sẽ rời khỏi server này và StudyPulse sẽ không thể đọc tin nhắn ở đó nữa cho đến khi được mời lại.`,
    );
    if (!confirmed) return;
    try {
      await disconnectDiscord(guildId);
      setPlatforms((current) =>
        current.map((platform) => {
          if (platform.id !== "discord") return platform;
          const guilds = (platform.guilds || []).filter((guild) => guild.id !== guildId);
          return { ...platform, guilds, connected: guilds.length > 0 };
        }),
      );
      notify(`Đã hủy kết nối server "${guildName}"`, "info");
    } catch (err) {
      notify(err instanceof ApiError ? err.message : "Không thể hủy kết nối, thử lại sau.", "error");
    }
  };

  const flagEvent = async (id) => {
    setBusyItemId(id);
    try {
      await flagTimelineItem(id);
      await mutateTimeline();
      notify("Đã đánh dấu sai và chuyển cho TA kiểm tra", "success");
    } catch (err) {
      notify(err instanceof ApiError ? err.message : "Không thể đánh dấu mục này, thử lại sau.", "error");
    } finally {
      setBusyItemId(null);
    }
  };

  const addToCalendar = async (id) => {
    setBusyItemId(id);
    try {
      const result = await confirmCalendar(id);
      notify(result.detail ? `Đã thêm vào Google Calendar: ${result.detail}` : "Đã thêm sự kiện vào Google Calendar", "success");
      await mutateTimeline();
    } catch (err) {
      notify(err instanceof ApiError ? err.message : "Không thể thêm vào lịch, thử lại sau.", "error");
    } finally {
      setBusyItemId(null);
    }
  };

  const saveEvent = async (id, time) => {
    try {
      await patchTimelineItem(id, { time });
      await mutateTimeline();
      setEditingEvent(null);
      notify("Đã lưu thay đổi của bạn", "success");
    } catch (err) {
      notify(err instanceof ApiError ? err.message : "Không thể lưu thay đổi, thử lại sau.", "error");
    }
  };

  const dashboardProps = {
    events,
    timelineLoading,
    timelineError,
    onRetryTimeline: () => mutateTimeline(),
    busyItemId,
    platforms,
    activeAction,
    onAction: handleAction,
    onCalendar: addToCalendar,
    onEdit: setEditingEvent,
    onFlag: flagEvent,
    onTogglePlatform: togglePlatform,
    onDisconnectGuild: disconnectDiscordGuild,
    outlookConnecting,
    showConnections,
    setShowConnections,
    googleUser,
  };

  const handleGoogleLogin = async () => {
    try {
      const authUrl = await getGoogleAuthUrl();
      window.location.href = authUrl;
    } catch (err) {
      notify(err instanceof ApiError ? err.message : "Không thể bắt đầu kết nối Google, kiểm tra backend.", "error");
    }
  };

  const handleGoogleLogout = async () => {
    const confirmed = window.confirm(
      "Đăng xuất khỏi tài khoản Google?\n\nStudyPulse sẽ không thể đọc email hoặc lịch của bạn cho đến khi bạn kết nối lại.",
    );
    if (!confirmed) return;
    try {
      await disconnectGoogle();
      setGoogleUser({ connected: false, email: null });
      try {
        localStorage.removeItem(GOOGLE_USER_CACHE_KEY);
      } catch {}
      setPlatforms((current) => current.map((p) => (p.id === "gmail" ? { ...p, connected: false } : p)));
      notify("Đã đăng xuất Google", "info");
    } catch (err) {
      notify(err instanceof ApiError ? err.message : "Không thể đăng xuất, thử lại sau.", "error");
    }
  };

  return (
    <main className="flex h-dvh flex-col overflow-hidden bg-canvas text-ink">
      <Header
        googleConnected={googleUser.connected}
        googleEmail={googleUser.email}
        onGoogleLogin={handleGoogleLogin}
        onGoogleLogout={handleGoogleLogout}
        onOpenConnections={() => { setShowConnections(true); setMobileView("dashboard"); }}
      />
      <div className="hidden min-h-0 flex-1 lg:flex">
        <ChatPanel
          messages={messages}
          onSend={sendMessage}
          isSending={isSending}
          sessions={sessions}
          activeConversationId={conversationId}
          onSelectSession={switchConversation}
          onNewSession={createNewConversation}
          onDeleteSession={deleteConversation}
        />
        <Dashboard {...dashboardProps} />
      </div>
      <div className="min-h-0 flex-1 lg:hidden">
        {mobileView === "chat" ? (
          <ChatPanel
            messages={messages}
            onSend={sendMessage}
            isSending={isSending}
            sessions={sessions}
            activeConversationId={conversationId}
            onSelectSession={switchConversation}
            onNewSession={createNewConversation}
            onDeleteSession={deleteConversation}
          />
        ) : (
          <Dashboard {...dashboardProps} />
        )}
      </div>
      <nav className="grid h-16 shrink-0 grid-cols-2 border-t border-slate-200 bg-white lg:hidden" aria-label="Điều hướng di động">
        <button onClick={() => setMobileView("dashboard")} className={`flex flex-col items-center justify-center gap-0.5 text-[10px] font-bold ${mobileView === "dashboard" ? "text-blue-600" : "text-slate-400"}`}><Icon>dashboard</Icon>Tổng quan</button>
        <button onClick={() => setMobileView("chat")} className={`flex flex-col items-center justify-center gap-0.5 text-[10px] font-bold ${mobileView === "chat" ? "text-blue-600" : "text-slate-400"}`}><Icon>smart_toy</Icon>Trợ lý AI</button>
      </nav>
      <EditDialog event={editingEvent} onClose={() => setEditingEvent(null)} onSave={saveEvent} />
      <OutlookDeviceCodeDialog deviceCode={outlookDeviceCode} onClose={() => setOutlookDeviceCode(null)} />
      {toast ? <Toast text={toast.text} type={toast.type} /> : null}
    </main>
  );
}
