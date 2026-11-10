// All calls to the FastAPI backend. Each function returns the JSON body or throws an
// Error whose message is the server's explanation (shown to the employee).

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : "تعذّر الاتصال بالخادم";
    throw new Error(detail);
  }
  return body;
}

const query = (params) => "?" + new URLSearchParams(params).toString();

export const api = {
  employees: () => request("/api/employees"),
  resources: () => request("/api/resources"),
  actions: () => request("/api/actions"),
  documents: (employeeId) => request("/api/documents" + query({ employee_id: employeeId })),
  requests: (employeeId) => request("/api/requests" + query({ employee_id: employeeId })),
  conversations: (employeeId) =>
    request("/api/conversations" + query({ employee_id: employeeId })),
  messages: (conversationId, employeeId) =>
    request(`/api/conversations/${conversationId}` + query({ employee_id: employeeId })),
  startQuestion: (employeeId, question, conversationId) =>
    request("/api/ask/jobs", {
      method: "POST",
      body: JSON.stringify({
        employee_id: employeeId,
        question,
        conversation_id: conversationId ?? null,
      }),
    }),
  questionStatus: (jobId) => request(`/api/ask/jobs/${jobId}`),
  requestAccess: (employeeId, resourceId, actionId) =>
    request("/api/access", {
      method: "POST",
      body: JSON.stringify({
        employee_id: employeeId,
        resource_id: resourceId,
        action_id: actionId,
      }),
    }),
};

// Ask the server every few seconds until the answer is ready.
export async function waitForAnswer(jobId, intervalMs = 2500) {
  for (;;) {
    const job = await api.questionStatus(jobId);
    if (job.status === "done") return job.result;
    if (job.status === "error") throw new Error(job.error || "تعذّر توليد الإجابة");
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}
