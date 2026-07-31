import { Icon } from "../common/Icon.jsx";
import { REVOCABLE_PLATFORM_IDS } from "../../constants/chat.js";

export function Connections({ platforms, onToggle, onDisconnectGuild, outlookConnecting, ingestStatus = {} }) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-panel">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-blue-600">Thiết lập dữ liệu</p>
          <h2 className="mt-1 text-xl font-extrabold tracking-tight text-ink">Kết nối nền tảng</h2>
          <p className="mt-2 text-sm leading-6 text-slate-500">Cấp quyền để StudyPulse gom thông báo học tập về một nơi.</p>
        </div>
        <div className="grid size-11 place-items-center rounded-2xl bg-blue-50 text-blue-600"><Icon>hub</Icon></div>
      </div>
      <div className="mt-6 divide-y divide-slate-100">
        {platforms.map((platform) => {
          const isDiscord = platform.id === "discord";
          const isOutlook = platform.id === "outlook";
          const buttonLabel =
            isOutlook && outlookConnecting
              ? "Đang chờ đăng nhập…"
              : platform.connected
                ? isDiscord
                  ? "Kết nối"
                  : REVOCABLE_PLATFORM_IDS.has(platform.id)
                    ? "Hủy kết nối"
                    : "Quản lý"
                : "Kết nối";
          const isDanger = platform.connected && !isDiscord && REVOCABLE_PLATFORM_IDS.has(platform.id);
          const isSyncing = ingestStatus[platform.id]?.status === "running";
          return (
            <div key={platform.id} className="py-4">
              <div className="flex items-center gap-3">
                <div className="grid size-11 shrink-0 place-items-center rounded-2xl bg-slate-100 text-slate-600"><Icon>{platform.icon}</Icon></div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="font-bold text-ink">{platform.name}</p>
                    <span className={`size-2 rounded-full ${platform.connected ? "bg-emerald-500" : "bg-slate-300"}`} />
                  </div>
                  <p className="truncate text-xs text-slate-500">
                    {isDiscord && platform.guilds?.length ? platform.guilds.map((g) => g.name).join(", ") : platform.scope}
                  </p>
                </div>
                <button
                  onClick={() => onToggle(platform.id)}
                  disabled={platform.id === "zalo" || (isOutlook && outlookConnecting)}
                  className={`rounded-xl px-3 py-2 text-xs font-bold transition-colors ${
                    isDanger
                      ? "bg-red-50 text-red-600 hover:bg-red-100"
                      : platform.connected
                        ? "bg-slate-100 text-slate-600 hover:bg-slate-200"
                        : "bg-blue-600 text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
                  }`}
                >
                  {buttonLabel}
                </button>
              </div>
              {isSyncing ? (
                <div className="ml-14 mt-2">
                  <div className="flex items-center gap-1.5 text-[11px] font-semibold text-blue-600">
                    <Icon className="animate-spin text-sm">progress_activity</Icon>
                    Đang tải dữ liệu mới…
                  </div>
                  <div className="mt-1.5 h-1.5 w-full animate-pulse rounded-full bg-blue-200" />
                </div>
              ) : null}
              {isDiscord && platform.guilds?.length ? (
                <ul className="ml-14 mt-2 space-y-1.5">
                  {platform.guilds.map((guild) => (
                    <li key={guild.id} className="flex items-center justify-between gap-2 rounded-xl bg-slate-50 px-3 py-1.5">
                      <span className="truncate text-xs font-semibold text-slate-600">{guild.name}</span>
                      <button
                        onClick={() => onDisconnectGuild(guild.id, guild.name)}
                        className="shrink-0 rounded-lg px-2 py-1 text-[11px] font-bold text-red-600 transition-colors hover:bg-red-50"
                      >
                        Hủy kết nối
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          );
        })}
      </div>
      <div className="mt-4 flex items-start gap-3 rounded-2xl bg-emerald-50 p-4 text-emerald-800">
        <Icon className="text-xl">shield_lock</Icon>
        <p className="text-xs leading-5"><strong>Quyền riêng tư:</strong> StudyPulse chỉ đọc nguồn bạn cấp quyền và không tự gửi email hay tin nhắn.</p>
      </div>
    </div>
  );
}
