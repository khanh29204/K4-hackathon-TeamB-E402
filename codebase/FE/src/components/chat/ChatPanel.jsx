import { useEffect, useRef, useState } from "react";
import { Icon } from "../common/Icon.jsx";
import { MessageBubble } from "./MessageBubble.jsx";

export function ChatPanel({
  messages,
  onSend,
  isSending,
  sessions = [],
  activeConversationId,
  onSelectSession,
  onNewSession,
  onDeleteSession,
}) {
  const [value, setValue] = useState("");
  const [showHistoryMenu, setShowHistoryMenu] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    messagesEndRef.current?.scrollIntoView({
      behavior: prefersReducedMotion ? "auto" : "smooth",
      block: "end",
    });
  }, [messages.length]);

  const submit = (event) => {
    event.preventDefault();
    const text = value.trim();
    if (!text || isSending) return;
    onSend(text);
    setValue("");
  };

  const activeSession = sessions.find((s) => s.id === activeConversationId);

  return (
    <section className="relative flex min-h-0 flex-1 flex-col bg-white lg:max-w-[40%] lg:border-r lg:border-slate-200/80" aria-label="Trò chuyện với StudyPulse">
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5">
        <div>
          <h2 className="font-extrabold text-ink truncate max-w-[180px]">
            {activeSession?.title || "Trợ lý của bạn"}
          </h2>
          <div className="mt-0.5 flex items-center gap-1.5 text-xs text-emerald-700">
            <span className="size-2 rounded-full bg-emerald-500" />
            Sẵn sàng hỗ trợ
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            onClick={onNewSession}
            className="flex items-center gap-1 rounded-xl bg-blue-50 px-2.5 py-1.5 text-xs font-bold text-blue-600 transition-colors hover:bg-blue-100"
            title="Tạo cuộc hội thoại mới"
          >
            <Icon className="text-base">add</Icon>
            <span className="hidden sm:inline">Mới</span>
          </button>

          <div className="relative">
            <button
              onClick={() => setShowHistoryMenu(!showHistoryMenu)}
              className={`flex items-center gap-1 rounded-xl border px-2.5 py-1.5 text-xs font-bold transition-colors ${
                showHistoryMenu ? "border-blue-400 bg-blue-50 text-blue-700" : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
              }`}
              title="Xem lịch sử trò chuyện"
            >
              <Icon className="text-base">history</Icon>
              <span>Lịch sử</span>
            </button>

            {showHistoryMenu && (
              <div className="absolute right-0 top-full z-50 mt-2 w-72 rounded-2xl border border-slate-200 bg-white p-2 shadow-xl animate-in fade-in zoom-in-95">
                <div className="flex items-center justify-between px-3 py-2 border-b border-slate-100">
                  <span className="text-xs font-extrabold text-ink">Lịch sử cuộc hội thoại</span>
                  <button
                    onClick={onNewSession}
                    className="text-xs font-bold text-blue-600 hover:underline flex items-center gap-0.5"
                  >
                    <Icon className="text-sm">add</Icon> Mới
                  </button>
                </div>
                <div className="max-h-64 overflow-y-auto space-y-1 py-1.5">
                  {sessions.length === 0 ? (
                    <p className="px-3 py-4 text-center text-xs text-slate-400">Chưa có lịch sử hội thoại</p>
                  ) : (
                    sessions.map((session) => {
                      const isActive = session.id === activeConversationId;
                      return (
                        <div
                          key={session.id}
                          className={`group flex items-center justify-between rounded-xl px-3 py-2 text-xs transition-colors cursor-pointer ${
                            isActive ? "bg-blue-50 text-blue-700 font-bold" : "text-slate-700 hover:bg-slate-50"
                          }`}
                          onClick={() => {
                            onSelectSession(session.id);
                            setShowHistoryMenu(false);
                          }}
                        >
                          <div className="flex-1 truncate pr-2">
                            <p className="truncate">{session.title || "Cuộc hội thoại mới"}</p>
                            <p className="text-[10px] text-slate-400">{session.updatedAt ? new Date(session.updatedAt).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }) : ""}</p>
                          </div>
                          {sessions.length > 1 && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                onDeleteSession(session.id);
                              }}
                              className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-red-500 rounded transition-opacity"
                              title="Xóa cuộc hội thoại"
                            >
                              <Icon className="text-sm">delete</Icon>
                            </button>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="chat-scroll flex-1 space-y-5 overflow-y-auto px-5 py-6" aria-live="polite">
        <div className="rounded-2xl border border-blue-100 bg-blue-50/60 p-4">
          <div className="mb-2 flex items-center gap-2 text-xs font-bold text-blue-700">
            <Icon className="text-lg">verified_user</Icon>
            Phạm vi hỗ trợ
          </div>
          <p className="text-sm leading-6 text-slate-600">Mình tổng hợp lịch, deadline và link học. Mình không nộp bài hoặc trả lời tin nhắn thay bạn.</p>
        </div>
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} onRetry={onSend} />
        ))}
        <div ref={messagesEndRef} aria-hidden="true" />
      </div>

      <form onSubmit={submit} className="relative border-t border-slate-100 bg-white p-4">
        {isSending && (
          <div className="absolute top-0 left-0 right-0 h-0.5 overflow-hidden bg-blue-100">
            <div className="h-full bg-gradient-to-r from-blue-500 to-indigo-600 w-1/3 progress-line-shimmer" />
          </div>
        )}
        <div className="flex items-end gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-2 transition-colors focus-within:border-blue-400 focus-within:ring-4 focus-within:ring-blue-50">
          <button type="button" className="grid size-10 shrink-0 place-items-center rounded-xl text-slate-400 hover:bg-white" aria-label="Đính kèm">
            <Icon>attach_file</Icon>
          </button>
          <label className="sr-only" htmlFor="chat-input">Nhập câu hỏi</label>
          <textarea
            id="chat-input"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) submit(event);
            }}
            rows="1"
            placeholder="Hỏi về lịch hoặc deadline..."
            className="max-h-28 min-h-10 flex-1 resize-none bg-transparent py-2 text-sm text-ink outline-none placeholder:text-slate-400"
          />
          <button
            type="submit"
            className="grid size-10 shrink-0 place-items-center rounded-xl bg-blue-600 text-white transition-colors hover:bg-blue-700 disabled:opacity-40"
            disabled={!value.trim() || isSending}
            aria-label="Gửi"
          >
            {isSending ? (
              <span className="size-4 animate-spin rounded-full border-2 border-white/40 border-t-white" aria-hidden="true" />
            ) : (
              <Icon className="text-xl">arrow_upward</Icon>
            )}
          </button>
        </div>
        <p className="mt-2 text-center text-[10px] text-slate-400">Kết quả AI có thể chưa chính xác. Hãy kiểm tra nguồn gốc trước khi xác nhận.</p>
      </form>
    </section>
  );
}
