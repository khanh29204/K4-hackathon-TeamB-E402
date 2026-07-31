import { useDeferredValue, useMemo, useState } from "react";
import { Icon } from "../common/Icon.jsx";
import { QuickActions } from "./QuickActions.jsx";
import { Connections } from "./Connections.jsx";
import { EventCard } from "./EventCard.jsx";
import { HitlReview } from "./HitlReview.jsx";
import { TimelineSkeleton } from "./TimelineSkeleton.jsx";
import { TimelineError } from "./TimelineError.jsx";

export function Dashboard({
  events,
  timelineLoading,
  timelineError,
  onRetryTimeline,
  busyItemId,
  platforms,
  activeAction,
  onAction,
  onCalendar,
  onEdit,
  onFlag,
  onTogglePlatform,
  onDisconnectGuild,
  outlookConnecting,
  ingestStatus,
  showConnections,
  setShowConnections,
  hitlItems,
  onApproveHitl,
  onRejectHitl,
  hitlBusyItemId,
  showHitl,
  setShowHitl,
}) {
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const filteredEvents = useMemo(() => {
    const normalized = deferredQuery.trim().toLocaleLowerCase("vi");
    let list = events;
    if (activeAction === "discord") list = list.filter((event) => event.source === "Discord");
    if (activeAction === "today") list = list.filter((event) => event.date === "Hôm nay");
    if (activeAction === "important") list = list.filter((event) => event.priority === "Khẩn cấp");
    if (!normalized) return list;
    return list.filter((event) => `${event.title} ${event.course} ${event.source}`.toLocaleLowerCase("vi").includes(normalized));
  }, [activeAction, deferredQuery, events]);

  return (
    <section className="dashboard-scroll min-h-0 flex-1 overflow-y-auto bg-canvas px-4 py-5 md:px-6 lg:px-7" aria-label="Dashboard học tập">
      <div className="mx-auto max-w-5xl">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
          <div>
            <p className="text-sm font-semibold text-slate-500">Thứ Năm, 30 tháng 7</p>
            <h2 className="mt-1 text-2xl font-extrabold tracking-tight text-ink md:text-3xl">Chào buổi chiều, Minh 👋</h2>
            <p className="mt-2 text-sm text-slate-500">Hỏi StudyPulse ở khung chat để bắt đầu tổng hợp deadline và lịch học thật.</p>
          </div>
          <div className="flex w-fit flex-wrap gap-2">
            {hitlItems.length > 0 ? (
              <button onClick={() => { setShowHitl(!showHitl); setShowConnections(false); }} className="flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-xs font-bold text-amber-700 shadow-sm transition-colors hover:border-amber-300">
                <Icon className="text-lg">warning</Icon>Cần duyệt ({hitlItems.length})
              </button>
            ) : null}
            <button onClick={() => { setShowConnections(!showConnections); setShowHitl(false); }} className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-bold text-slate-700 shadow-sm transition-colors hover:border-blue-300">
              <Icon className="text-lg">settings_input_component</Icon>Quản lý kết nối
            </button>
          </div>
        </div>

        <div className="mt-6">
          <QuickActions active={activeAction} onSelect={onAction} />
        </div>

        {showHitl ? (
          <div className="mt-6">
            <h2 className="text-lg font-extrabold text-ink">Mục cần duyệt</h2>
            <p className="mt-1 text-xs text-slate-500">Trích xuất mơ hồ hoặc có mâu thuẫn — StudyPulse sẽ không tự thêm vào dòng thời gian cho đến khi bạn xác nhận.</p>
            <HitlReview items={hitlItems} onApprove={onApproveHitl} onReject={onRejectHitl} busyItemId={hitlBusyItemId} />
          </div>
        ) : showConnections ? (
          <div className="mt-6"><Connections platforms={platforms} onToggle={onTogglePlatform} onDisconnectGuild={onDisconnectGuild} outlookConnecting={outlookConnecting} ingestStatus={ingestStatus} /></div>
        ) : (
          <>
            <div className="mt-7 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
              <div>
                <h2 className="text-lg font-extrabold text-ink">Dòng thời gian học tập</h2>
                <p className="mt-1 text-xs text-slate-500">{filteredEvents.length} thông báo được tổng hợp từ tool thật</p>
              </div>
              <div className="relative">
                <Icon className="absolute left-3 top-1/2 -translate-y-1/2 text-lg text-slate-400">search</Icon>
                <label className="sr-only" htmlFor="event-search">Tìm thông báo</label>
                <input id="event-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Tìm môn học, nguồn..." className="h-10 w-full rounded-xl border border-slate-200 bg-white pl-10 pr-4 text-xs outline-none transition-colors focus:border-blue-400 focus:ring-4 focus:ring-blue-50 sm:w-60" />
              </div>
            </div>

            {timelineError ? (
              <TimelineError onRetry={onRetryTimeline} />
            ) : timelineLoading ? (
              <TimelineSkeleton />
            ) : (
              <div className="mt-4 space-y-3">
                {filteredEvents.length > 0 ? (
                  filteredEvents.map((event) => (
                    <EventCard key={event.id} event={event} onCalendar={onCalendar} onEdit={onEdit} onFlag={onFlag} isBusy={busyItemId === event.id} />
                  ))
                ) : events.length === 0 ? (
                  <div className="rounded-3xl border border-dashed border-slate-300 bg-white p-10 text-center">
                    <Icon className="text-4xl text-slate-300">chat</Icon>
                    <p className="mt-3 text-sm font-bold text-slate-600">Chưa có dữ liệu thật nào được tổng hợp</p>
                    <p className="mt-1 text-xs text-slate-400">Bấm một mục nhanh ở trên, hoặc hỏi StudyPulse ở khung chat bên trái.</p>
                  </div>
                ) : (
                  <div className="rounded-3xl border border-dashed border-slate-300 bg-white p-10 text-center">
                    <Icon className="text-4xl text-slate-300">search_off</Icon>
                    <p className="mt-3 text-sm font-bold text-slate-600">Không tìm thấy thông báo phù hợp</p>
                    <button onClick={() => { setQuery(""); onAction("week"); }} className="mt-3 text-xs font-bold text-blue-600">Xóa bộ lọc</button>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
