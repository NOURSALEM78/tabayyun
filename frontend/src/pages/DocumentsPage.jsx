// The documents in force this employee may see (the same rule the search uses).
import { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";

export default function DocumentsPage({ employee }) {
  const [documents, setDocuments] = useState([]);
  const [search, setSearch] = useState("");
  const [level, setLevel] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api.documents(employee.employee_id).then(setDocuments).catch((e) => setError(e.message));
  }, [employee.employee_id]);

  const levels = useMemo(() => [...new Set(documents.map((d) => d.classification))], [documents]);
  const shown = documents.filter(
    (d) => d.title.includes(search.trim()) && (!level || d.classification === level)
  );

  return (
    <section className="page">
      <header className="top">
        <h2>مستنداتي</h2>
        <p>الأنظمة واللوائح المتاحة لصلاحيتك</p>
      </header>
      <div className="content">
        {error && <div className="banner error">{error}</div>}
        <div className="tools">
          <input placeholder="ابحث في المستندات…" value={search} onChange={(e) => setSearch(e.target.value)} />
          <select value={level} onChange={(e) => setLevel(e.target.value)}>
            <option value="">كل التصنيفات</option>
            {levels.map((l) => (
              <option key={l}>{l}</option>
            ))}
          </select>
        </div>
        <table>
          <thead>
            <tr>
              <th>المستند</th>
              <th>النوع</th>
              <th>الجهة المصدرة</th>
              <th>التصنيف</th>
              <th>الحالة</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((d) => (
              <tr key={d.doc_id}>
                <td>📄 {d.title}</td>
                <td>{d.doc_type}</td>
                <td>{d.issuer}</td>
                <td>
                  <span className="pill level">{d.classification}</span>
                </td>
                <td>
                  {d.status}
                  {d.has_amendments && <span className="pill amended-tag">عليه تعديلات</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {shown.length === 0 && !error && <p className="empty">لا توجد مستندات مطابقة.</p>}
        <p className="caption">يرى كل موظف المستندات التي تسمح بها صلاحيته فقط.</p>
      </div>
    </section>
  );
}
