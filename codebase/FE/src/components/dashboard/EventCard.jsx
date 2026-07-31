import { useState } from "react";
import { Icon } from "../common/Icon.jsx";

export function EventCard({ event, onCalendar, onEdit, onFlag, isBusy }) {
  const [showSource, setShowSource] = useState(false);
  const urgent = event.priority === "Khẩn cấp";
  const review = !event.verified;

  return (
    <article className={`event-card card-enter rounded-2xl border bg-white p-4 transition-shadow hover:shadow-md ${review ? "border-amber-200" : "border-slate-200"}`}>
      <div className="flex gap-3">
        <div className={`grid size-11 shrink-0 place-items-center rounded-2xl ${
          event.type === "deadline" ? "bg-orange-50 text-orange-600" : review ? "bg-amber-50 text-amber-600" : "bg-blue-50 text-blue-600"
        }`}>
          <Icon>{event.type === "deadline" ? "assignment" : review ? "question_mark" : "event"}</Icon>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">{event.course || "Chưa rõ môn học"}</p>
              <h3 className="mt-1 text-sm font-extrabold leading-5 text-ink">{event.title}</h3>
            </div>
            <span className={`rounded-full px-2.5 py-1 text-[10px] font-extrabold ${
              urgent ? "bg-red-50 text-red-600" : review ? "bg-amber-50 text-amber-700" : "bg-slate-100 text-slate-600"
            }`}>
              {event.priority}
            </span>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-600">
            <span className="flex items-center gap-1.5 font-bold text-slate-700"><Icon className="text-base">schedule</Icon>{event.date} · {event.time}</span>
            {event.source_url ? (
              <a
                href={event.source_url}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1.5 text-blue-600 hover:underline"
              >
                <Icon className="text-base">{event.sourceIcon}</Icon>{event.source}
              </a>
            ) : (
              <span className="flex items-center gap-1.5"><Icon className="text-base">{event.sourceIcon}</Icon>{event.source}</span>
            )}
            <span className={`flex items-center gap-1.5 ${review ? "text-amber-700" : "text-emerald-700"}`}>
              <Icon className="text-base">{review ? "warning" : "verified"}</Icon>{event.confidence}% tin cậy
            </span>
          </div>
          <p className="mt-3 text-xs leading-5 text-slate-500">{event.detail}</p>
          {event.raw_snippet ? (
            <button onClick={() => setShowSource(!showSource)} className="mt-2 flex items-center gap-1 text-[11px] font-bold text-blue-600 hover:underline">
              <Icon className="text-sm">{showSource ? "expand_less" : "expand_more"}</Icon>
              {showSource ? "Ẩn nguồn gốc" : event.action || "Xem nguồn gốc"}
            </button>
          ) : null}
          {showSource && event.raw_snippet ? (
            <p className="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-xl bg-slate-50 p-3 text-xs leading-5 text-slate-500">{event.raw_snippet}</p>
          ) : null}
          <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
            <span className="hidden flex-1 sm:block" />
            <button onClick={() => onEdit(event)} className="rounded-lg px-2 py-1 text-xs font-bold text-slate-500 transition-colors hover:bg-slate-100">
              Chỉnh sửa
            </button>
            <button onClick={() => onFlag(event.id)} disabled={isBusy} className="rounded-lg px-2 py-1 text-xs font-bold text-slate-500 transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-40">
              Đánh dấu sai
            </button>
            <button
              onClick={() => onCalendar(event.id)}
              disabled={isBusy}
              className="flex items-center gap-1 rounded-xl bg-slate-900 px-3 py-2 text-xs font-bold text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
            >
              <Icon className="text-base">calendar_add_on</Icon>Thêm vào lịch
            </button>
          </div>
        </div>
      </div>
    </article>
  );
}
