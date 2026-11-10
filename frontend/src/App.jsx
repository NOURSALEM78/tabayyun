// The page frame: sidebar on the right (RTL) and the chosen page on the left.
// The chosen employee stands in for login in this demo version.
import { useCallback, useEffect, useState } from "react";
import { api } from "./api.js";
import Sidebar from "./components/Sidebar.jsx";
import ChatPage from "./pages/ChatPage.jsx";
import DocumentsPage from "./pages/DocumentsPage.jsx";
import RequestsPage from "./pages/RequestsPage.jsx";

const SAVED_EMPLOYEE = "tabayyun.employee";

function savedEmployee() {
  try {
    return localStorage.getItem(SAVED_EMPLOYEE);
  } catch {
    return null;
  }
}

export default function App() {
  const [employees, setEmployees] = useState([]);
  const [employeeId, setEmployeeId] = useState(savedEmployee);
  const [page, setPage] = useState("chat");
  const [conversations, setConversations] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .employees()
      .then((list) => {
        setEmployees(list);
        setEmployeeId((current) =>
          list.some((e) => e.employee_id === current) ? current : list[0]?.employee_id
        );
      })
      .catch((e) => setError(e.message));
  }, []);

  const refreshConversations = useCallback(() => {
    if (!employeeId) return;
    api.conversations(employeeId).then(setConversations).catch(() => setConversations([]));
  }, [employeeId]);

  useEffect(() => {
    try {
      if (employeeId) localStorage.setItem(SAVED_EMPLOYEE, employeeId);
    } catch {
      /* storage unavailable: the choice is simply not remembered */
    }
    setConversationId(null);
    refreshConversations();
  }, [employeeId, refreshConversations]);

  const employee = employees.find((e) => e.employee_id === employeeId);

  return (
    <div className="app">
      <Sidebar
        page={page}
        onPage={setPage}
        employees={employees}
        employee={employee}
        onEmployee={setEmployeeId}
        conversations={conversations}
        conversationId={conversationId}
        onConversation={(id) => {
          setConversationId(id);
          setPage("chat");
        }}
        onNewConversation={() => {
          setConversationId(null);
          setPage("chat");
        }}
      />
      <main>
        {error && <div className="banner error">{error}</div>}
        {employee && page === "chat" && (
          <ChatPage
            key={employee.employee_id}
            employee={employee}
            conversationId={conversationId}
            onConversationStarted={(id) => {
              setConversationId(id);
              refreshConversations();
            }}
            onAnswered={refreshConversations}
          />
        )}
        {employee && page === "documents" && <DocumentsPage employee={employee} />}
        {employee && page === "requests" && <RequestsPage employee={employee} />}
      </main>
    </div>
  );
}
