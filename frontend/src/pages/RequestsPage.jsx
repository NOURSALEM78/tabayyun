// Access requests: the employee's list, and a form whose decision comes from the
// decision matrix at once (the language model is not involved).
import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";

const TABS = [
  { id: "all", label: "الكل", match: () => true },
  { id: "pending", label: "بانتظار الموافقة", match: (r) => r.status === "pending" },
  { id: "allowed", label: "مسموح", match: (r) => r.decision === "allowed" },
  { id: "denied", label: "مرفوض", match: (r) => r.decision === "denied" },
];
const DECISION_CLASS = { allowed: "ok", requires_approval: "warn", denied: "bad" };

function statusLabel(r) {
  return r.status === "pending" ? "بانتظار الموافقة" : r.decision_label;
}

export default function RequestsPage({ employee }) {
  const [requests, setRequests] = useState([]);
  const [tab, setTab] = useState("all");
  const [formOpen, setFormOpen] = useState(false);
  const [resources, setResources] = useState([]);
  const [actions, setActions] = useState([]);
  const [resourceId, setResourceId] = useState("");
  const [actionId, setActionId] = useState("");
  const [decision, setDecision] = useState(null);
  const [error, setError] = useState("");

  const refresh = useCallback(
    () => api.requests(employee.employee_id).then(setRequests).catch((e) => setError(e.message)),
    [employee.employee_id]
  );
  useEffect(() => {
    refresh();
    setDecision(null);
  }, [refresh]);

  useEffect(() => {
    api.resources().then((list) => {
      setResources(list);
      setResourceId(list[0]?.resource_id ?? "");
    });
    api.actions().then((list) => {
      setActions(list);
      setActionId(list[0]?.action_id ?? "");
    });
  }, []);

  async function submit(e) {
    e.preventDefault();
    setError("");
    try {
      setDecision(await api.requestAccess(employee.employee_id, resourceId, actionId));
      refresh();
    } catch (failure) {
      setError(failure.message);
    }
  }

  const current = TABS.find((t) => t.id === tab);
  const pendingCount = requests.filter((r) => r.status === "pending").length;

  return (
    <section className="page">
      <header className="top">
        <div>
          <h2>طلباتي</h2>
          <p>طلبات الاطلاع والتحميل والتعديل والمشاركة وحالتها</p>
        </div>
        <button className="btn" onClick={() => setFormOpen(!formOpen)}>
          {formOpen ? "إغلاق" : "+ طلب جديد"}
        </button>
      </header>
      <div className="content">
        {error && <div className="banner error">{error}</div>}

        {formOpen && (
          <form className="panel" onSubmit={submit}>
            <h4>طلب جديد</h4>
            <label>المورد</label>
            <select value={resourceId} onChange={(e) => setResourceId(e.target.value)}>
              {resources.map((r) => (
                <option key={r.resource_id} value={r.resource_id}>
                  {r.name} — {r.classification}
                </option>
              ))}
            </select>
            <label>الإجراء</label>
            <select value={actionId} onChange={(e) => setActionId(e.target.value)}>
              {actions.map((a) => (
                <option key={a.action_id} value={a.action_id}>
                  {a.name}
                </option>
              ))}
            </select>
            <button className="btn" type="submit">
              إرسال الطلب
            </button>

            {decision && (
              <div className={"decision " + DECISION_CLASS[decision.decision]}>
                <h3>
                  <span className="pill">{decision.decision_label}</span> {decision.action_name} —{" "}
                  {decision.resource_name}
                </h3>
                <div className="rows">
                  <span>السبب</span>
                  <span>{decision.explanation}</span>
                  {decision.approver && (
                    <>
                      <span>المعتمِد</span>
                      <span>{decision.approver}</span>
                    </>
                  )}
                  <span>السند</span>
                  <span>{decision.article ?? decision.legal_basis}</span>
                  <span>رقم الطلب</span>
                  <span>
                    {decision.request_id} · {decision.status === "pending" ? "بانتظار الموافقة" : "قرار تلقائي"}
                  </span>
                </div>
                <div className="next">{decision.next_step}</div>
              </div>
            )}
          </form>
        )}

        <div className="tabs">
          {TABS.map((t) => (
            <button key={t.id} className={tab === t.id ? "on" : ""} onClick={() => setTab(t.id)}>
              {t.label}
              {t.id === "pending" && pendingCount > 0 ? ` (${pendingCount})` : ""}
            </button>
          ))}
        </div>
        <table>
          <thead>
            <tr>
              <th>رقم الطلب</th>
              <th>المورد</th>
              <th>الإجراء</th>
              <th>القرار</th>
              <th>المعتمِد</th>
              <th>التاريخ</th>
            </tr>
          </thead>
          <tbody>
            {requests.filter(current.match).map((r) => (
              <tr key={r.request_id}>
                <td>{r.request_id}</td>
                <td>{r.resource_name}</td>
                <td>{r.action_name}</td>
                <td>
                  <span className={"pill " + DECISION_CLASS[r.decision]}>{statusLabel(r)}</span>
                </td>
                <td>{r.approver ?? "—"}</td>
                <td>{new Date(r.created_at).toLocaleDateString("ar-SA-u-ca-gregory")}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {requests.filter(current.match).length === 0 && <p className="empty">لا توجد طلبات.</p>}
      </div>
    </section>
  );
}
