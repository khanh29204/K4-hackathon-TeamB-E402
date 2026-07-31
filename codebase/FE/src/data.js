export const quickActions = [
  { id: "important", label: "Mail quan trọng", icon: "mark_email_unread", color: "text-blue-600 bg-blue-50" },
  { id: "discord", label: "Discord BTC", icon: "forum", color: "text-indigo-600 bg-indigo-50" },
  { id: "today", label: "Lịch hôm nay", icon: "today", color: "text-emerald-600 bg-emerald-50" },
  { id: "week", label: "Deadline tuần", icon: "assignment", color: "text-orange-600 bg-orange-50" },
];

export const initialEvents = [];

export const initialPlatforms = [
  { id: "gmail", name: "Gmail", icon: "mail", connected: false, scope: "Mail, Google Calendar" },
  { id: "outlook", name: "Outlook", icon: "alternate_email", connected: false, scope: "Mail, Calendar (chỉ đọc)" },
  { id: "discord", name: "Discord", icon: "forum", connected: false, scope: "Server BTC, Class K4", guilds: [] },
];

export const initialMessages = [
  {
    id: "welcome",
    role: "assistant",
    text: "Xin chào! Mình là trợ lý StudyPulse AI. Đăng nhập Google ở góc trên bên phải để bắt đầu quét email, tổng hợp lịch học và deadline nhé!",
    time: "",
  },
];
