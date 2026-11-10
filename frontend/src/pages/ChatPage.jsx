// The assistant: a conversation with the employee. A question is sent as a background
// job and the page polls until the answer is ready, so long model times are fine.
import { useEffect, useRef, useState } from "react";
import { api, waitForAnswer } from "../api.js";
import AssistantMessage from "../components/AssistantMessage.jsx";

const SUGGESTIONS = [
  "كم مدة التبليغ عن الوفاة؟",
  "هل يجوز نقل السجلات المدنية من مكاتب الأحوال المدنية؟",
  "هل تفقد المرأة السعودية جنسيتها إذا تزوجت بأجنبي؟",
];

export default function ChatPage({ employee, conversationId, onConversationStarted, onAnswered }) {
  const [messages, setMessages] = useState([]); // {question, reply?, error?, pending?}
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const startedHere = useRef(null); // a conversation this page just created
  const bottom = useRef(null);

  // Load a conversation chosen in the sidebar (but not one this page just started).
  useEffect(() => {
    if (conversationId === startedHere.current && conversationId != null) return;
    startedHere.current = null;
    if (conversationId == null) {
      setMessages([]);
      return;
    }
    api
      .messages(conversationId, employee.employee_id)
      .then((rows) => setMessages(rows.map((m) => ({ question: m.question, reply: m.reply }))))
      .catch((e) => setMessages([{ question: "", error: e.message }]));
  }, [conversationId, employee.employee_id]);

  // Braces matter: newer browsers return a promise from scrollIntoView, and an effect
  // must not return anything but a cleanup function.
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(text) {
    const question = text.trim();
    if (question.length < 3 || busy) return;
    setDraft("");
    setBusy(true);
    setMessages((list) => [...list, { question, pending: true }]);
    const update = (change) =>
      setMessages((list) => list.map((m, i) => (i === list.length - 1 ? { ...m, ...change } : m)));
    try {
      const job = await api.startQuestion(employee.employee_id, question, conversationId);
      if (conversationId == null) {
        startedHere.current = job.conversation_id;
        onConversationStarted(job.conversation_id);
      }
      const reply = await waitForAnswer(job.job_id);
      update({ reply, pending: false });
      onAnswered();
    } catch (e) {
      update({ error: e.message, pending: false });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page chat-page">
      <header className="top">
        <h2>المساعد</h2>
        <p>اسأل عن نظام الأحوال المدنية ولائحته التنفيذية، ونظام الجنسية ولائحته التنفيذية</p>
      </header>

      <div className="chat">
        {messages.length === 0 && (
          <div className="welcome">
            <h3>أهلًا {employee.name.split(" ")[0]}</h3>
            <p>يجيب تبيّن من الأنظمة المتاحة لصلاحيتك، ويذكر المصدر بعد كل معلومة.</p>
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => send(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, index) => (
          <div key={index} className="exchange">
            {m.question && <div className="bubble user">{m.question}</div>}
            {m.pending && (
              <div className="typing">
                <span className="dot" />
                <span className="dot" />
                <span className="dot" />
                جارٍ البحث في الأنظمة وصياغة الإجابة… قد يستغرق ذلك دقيقة أو أكثر
              </div>
            )}
            {m.reply && <AssistantMessage reply={m.reply} />}
            {m.error && <div className="bubble bot error">{m.error}</div>}
          </div>
        ))}
        <div ref={bottom} />
      </div>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          send(draft);
        }}
      >
        <div className="input-box">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={busy ? "انتظر حتى تكتمل الإجابة…" : "اكتب سؤالك…"}
            disabled={busy}
          />
          <button type="submit" disabled={busy || draft.trim().length < 3} aria-label="إرسال">
            ➤
          </button>
        </div>
        <div className="note">
          الإجابات من النصوص النظامية المتاحة لك فقط. للمواد المعدّلة أو غير المتاحة تُعرض إحالة إلى
          الجهة المختصة.
        </div>
      </form>
    </section>
  );
}
