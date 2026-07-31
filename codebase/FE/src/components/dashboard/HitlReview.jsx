import { useState } from "react";
import { Icon } from "../common/Icon.jsx";

const SOURCE_ICON = { gmail: "mail", outlook: "alternate_email", discord: "forum", direct_input: "edit" };
const CATEGORY_LABEL = {
  deadline: "Deadline",
  schedule: "Lịch học",
  assignment: "Bài tập",
  announcement: "Thông báo",
  exam: "Thi cử",
  other: "Khác",
};
const ISSUE_LABEL = {
  empty_title: "Thiếu tiêu đề",
  date_in_past: "Ngày đã qua",
  invalid_date_format: "Ngày không hợp lệ",
  invalid_category: "Loại không hợp lệ",
  duplicate_detected: "Có thể trùng lặp",
  below_minimum_confidence: "Độ tin cậy quá thấp",
};

export function HitlReview({ items, onApprove, onReject, busyItemId }) {
  const [expanded, setExpanded] = useState(null);

  if (!items.length) {
    return (
      <div className="rounded-3xl border border-dashed border-slate-300 bg-white p-10 text-center">
        <Icon className="text-4xl text-slate-300">task_alt</Icon>
        <p className="mt-3 text-sm font-bold text-slate-600">Không có mục nào cần duyệt</p>
        <p className="mt-1 text-xs text-slate-400">Các mục trích xuất mơ hồ hoặc có mâu thuẫn sẽ xuất hiện ở đây để bạn xác nhận.</p>
      </div>
    );
  }

  return (
    <div className="mt-4 space-y-3">
      {items.map((item) => {
        const isBusy = busyItemId === item.id;
        const isOpen = expanded === item.id;
        return (
          <article key={item.id} className="rounded-2xl border border-amber-200 bg-white p-4">
            <div className="flex gap-3">
              <div className="grid size-11 shrink-0 place-items-center rounded-2xl bg-amber-50 text-amber-600">
                <Icon>{SOURCE_ICON[item.source_platform] || "help"}</Icon>
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">{CATEGORY_LABEL[item.category] || item.category}</p>
                    <h3 className="mt-1 text-sm font-extrabold leading-5 text-ink">{item.title || "(Không có tiêu đề)"}</h3>
                  </div>
                  <span className="flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-1 text-[10px] font-extrabold text-amber-700">
                    <Icon className="text-sm">warning</Icon>{Math.round((item.confidence_score ?? 0) * 100)}% tin cậy
                  </span>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-600">
                  <span className="flex items-center gap-1.5 font-bold text-slate-700">
                    <Icon className="text-base">schedule</Icon>
                    {item.due_date ? `${item.due_date}${item.due_time ? ` · ${item.due_time}` : ""}` : "Chưa rõ ngày"}
                  </span>
                  <span className="flex items-center gap-1.5"><Icon className="text-base">{SOURCE_ICON[item.source_platform] || "help"}</Icon>{item.source_platform || "?"}</span>
                </div>
                {item.validation_issues?.length ? (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {item.validation_issues.map((issue) => (
                      <span key={issue} className="rounded-full bg-red-50 px-2 py-0.5 text-[10px] font-bold text-red-600">
                        {ISSUE_LABEL[issue] || issue}
                      </span>
                    ))}
                  </div>
                ) : null}
                {item.description ? <p className="mt-3 text-xs leading-5 text-slate-500">{item.description}</p> : null}
                {item.raw_snippet ? (
                  <button onClick={() => setExpanded(isOpen ? null : item.id)} className="mt-2 text-[11px] font-bold text-blue-600 hover:underline">
                    {isOpen ? "Ẩn văn bản gốc" : "Xem văn bản gốc"}
                  </button>
                ) : null}
                {isOpen && item.raw_snippet ? (
                  <p className="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-xl bg-slate-50 p-3 text-xs leading-5 text-slate-500">{item.raw_snippet}</p>
                ) : null}
                <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
                  <span className="hidden flex-1 sm:block" />
                  <button
                    onClick={() => onReject(item)}
                    disabled={isBusy}
                    className="rounded-lg px-3 py-2 text-xs font-bold text-slate-500 transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-40"
                  >
                    Từ chối
                  </button>
                  <button
                    onClick={() => onApprove(item)}
                    disabled={isBusy}
                    className="flex items-center gap-1 rounded-xl bg-slate-900 px-3 py-2 text-xs font-bold text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
                  >
                    <Icon className="text-base">check</Icon>Duyệt vào lịch
                  </button>
                </div>
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}
