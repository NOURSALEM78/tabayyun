// Right-hand sidebar: pages, conversations and the chosen employee.
const PAGES = [
  { id: "chat", label: "المساعد", icon: "💬" },
  { id: "documents", label: "مستنداتي", icon: "📁" },
  { id: "requests", label: "طلباتي", icon: "📋" },
];

function dayLabel(iso) {
  const day = new Date(iso);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (day.toDateString() === today.toDateString()) return "اليوم";
  if (day.toDateString() === yesterday.toDateString()) return "أمس";
  return day.toLocaleDateString("ar-SA-u-ca-gregory", { day: "numeric", month: "long" });
}

export default function Sidebar(props) {
  const { page, onPage, employees, employee, onEmployee } = props;
  const { conversations, conversationId, onConversation, onNewConversation } = props;

  let lastDay = "";
  return (
    <aside>
      <div className="logo">
        <span className="logo-mark">ت</span>تبيّن
      </div>

      <nav>
        {PAGES.map((item) => (
          <button
            key={item.id}
            className={page === item.id ? "nav-item on" : "nav-item"}
            onClick={() => onPage(item.id)}
          >
            <span>{item.icon}</span> {item.label}
          </button>
        ))}
      </nav>

      <div className="history">
        <button className="new-chat" onClick={onNewConversation}>
          + محادثة جديدة
        </button>
        {conversations.map((c) => {
          const day = dayLabel(c.updated_at);
          const heading = day !== lastDay ? <h4 key={"d" + c.conversation_id}>{day}</h4> : null;
          lastDay = day;
          return [
            heading,
            <button
              key={c.conversation_id}
              className={c.conversation_id === conversationId ? "chat-item on" : "chat-item"}
              onClick={() => onConversation(c.conversation_id)}
              title={c.title}
            >
              {c.title}
            </button>,
          ];
        })}
      </div>

      <div className="me">
        <div className="avatar">{employee?.name?.[0] ?? "؟"}</div>
        <div className="me-text">
          <select value={employee?.employee_id ?? ""} onChange={(e) => onEmployee(e.target.value)}>
            {employees.map((e) => (
              <option key={e.employee_id} value={e.employee_id}>
                {e.name} — {e.role_name}
              </option>
            ))}
          </select>
          <small>{employee?.role_name}</small>
          <span className="demo">وضع تجريبي: اختيار الموظف بدل تسجيل الدخول</span>
        </div>
      </div>
    </aside>
  );
}
