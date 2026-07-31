import { Icon } from "../common/Icon.jsx";
import { MarkdownText } from "../common/MarkdownText.jsx";
import { MeetingCard } from "./MeetingCard.jsx";

export function MessageBubble({ message, onRetry }) {
  const isUser = message.role === "user";
  const isClarification = message.needsClarification;
  const isError = message.isError;

  return (
    <div className={`message-enter flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      {!isUser ? (
        <div className="grid size-8 shrink-0 place-items-center rounded-xl bg-blue-600 text-white">
          <Icon className="text-lg">neurology</Icon>
        </div>
      ) : null}
      <div className={`max-w-[82%] ${isUser ? "text-right" : ""}`}>
        <div
          className={`inline-block rounded-2xl px-4 py-3 text-left text-sm leading-6 ${
            isUser
              ? "rounded-tr-sm bg-blue-600 text-white"
              : isError
                ? "rounded-tl-sm bg-red-50 text-red-700"
                : isClarification
                  ? "rounded-tl-sm bg-amber-50 text-amber-800"
                  : message.loading
                    ? "rounded-tl-sm bg-white border border-blue-200 thinking-glow text-slate-700 shadow-sm"
                    : "rounded-tl-sm bg-slate-100 text-slate-700"
          }`}
        >
          {message.loading ? (
            <div className="flex flex-col gap-2 min-w-[200px]">
              <div className="flex items-center gap-2 text-xs font-bold text-blue-600">
                <span className="flex gap-1 items-center">
                  <span className="size-1.5 rounded-full bg-blue-600 animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="size-1.5 rounded-full bg-blue-600 animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="size-1.5 rounded-full bg-blue-600 animate-bounce" style={{ animationDelay: "300ms" }} />
                </span>
                <span>{message.statusText || "StudyPulse đang phân tích dữ liệu..."}</span>
              </div>
              <div className="h-1 w-full bg-blue-100/70 rounded-full overflow-hidden relative">
                <div className="h-full bg-gradient-to-r from-blue-500 to-indigo-600 w-2/3 rounded-full progress-line-shimmer" />
              </div>
            </div>
          ) : isUser ? (
            message.text
          ) : (
            <MarkdownText text={message.text} />
          )}
        </div>
        {!isUser && message.calendarEvents?.length ? (
          <div className="mt-2 space-y-2 text-left">
            {message.calendarEvents.map((event) => (
              <MeetingCard key={event.id} event={event} />
            ))}
          </div>
        ) : null}
        {message.isError && message.retryText ? (
          <button
            onClick={() => onRetry(message.retryText)}
            className="mt-1.5 rounded-lg px-2 py-1 text-xs font-bold text-red-600 transition-colors hover:bg-red-50"
          >
            Thử lại
          </button>
        ) : (
          <p className="mt-1.5 text-[10px] font-medium text-slate-400">{message.time}</p>
        )}
      </div>
    </div>
  );
}
