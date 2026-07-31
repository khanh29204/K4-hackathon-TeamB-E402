import { useEffect, useRef, useState } from "react";
import { Icon } from "../common/Icon.jsx";
import { MessageBubble } from "./MessageBubble.jsx";

export function ChatPanel({ messages, onSend, isSending }) {
  const [value, setValue] = useState("");
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

  return (
    <section className="flex min-h-0 flex-1 flex-col bg-white lg:max-w-[40%] lg:border-r lg:border-slate-200/80" aria-label="Trò chuyện với StudyPulse">
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
        <div>
          <h2 className="font-extrabold text-ink">Trợ lý của bạn</h2>
          <div className="mt-0.5 flex items-center gap-1.5 text-xs text-emerald-700">
            <span className="size-2 rounded-full bg-emerald-500" />
            Sẵn sàng hỗ trợ
          </div>
        </div>
        <button className="grid size-9 place-items-center rounded-xl text-slate-400 hover:bg-slate-100" aria-label="Tùy chọn trò chuyện">
          <Icon>more_horiz</Icon>
        </button>
      </div>

      <div className="chat-scroll flex-1 space-y-5 overflow-y-auto px-5 py-6" aria-live="polite">
        <div className="rounded-2xl border border-blue-100 bg-blue-50/60 p-4">
          <div className="mb-2 flex items-center gap-2 text-xs font-bold text-blue-700">
            <Icon className="text-lg">verified_user</Icon>
            Phạm vi hỗ trợ
          </div>
          <p className="text-sm leading-6 text-slate-600">Mình tổng hợp lịch, deadline, tài liệu môn học, slide bài giảng, và quét/tóm tắt email, Discord học tập giúp bạn. Mình không nộp bài hoặc trả lời tin nhắn thay bạn.</p>
        </div>
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} onRetry={onSend} />
        ))}
        <div ref={messagesEndRef} aria-hidden="true" />
      </div>

      <form onSubmit={submit} className="border-t border-slate-100 bg-white p-4">
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
            placeholder="Hỏi về lịch, deadline, tài liệu môn học..."
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
