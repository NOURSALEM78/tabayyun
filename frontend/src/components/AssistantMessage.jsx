// One reply from the system: the checked answer, then amended-article notices,
// referrals and the sources. Citations such as [1] become small numbered badges.
function withCitations(text) {
  return text.split(/(\[\d+\])/g).map((part, index) => {
    const match = part.match(/^\[(\d+)\]$/);
    return match ? (
      <span key={index} className="cite">
        {match[1]}
      </span>
    ) : (
      part
    );
  });
}

export default function AssistantMessage({ reply }) {
  return (
    <div className="bubble bot">
      {reply.answer && <p className={reply.verified ? "" : "muted"}>{withCitations(reply.answer)}</p>}

      {/* Articles quoted word for word when the model's answer failed the checks;
          the first is open, the others can be opened one by one. */}
      {reply.quoted.map((item, index) => (
        <details key={item.number} className="quoted" open={index === 0}>
          <summary>
            <span className="cite">{item.number}</span> {item.citation}
          </summary>
          <div>«{item.text}»</div>
        </details>
      ))}

      {reply.amended.map((item) => (
        <div key={item.number} className="amended">
          <b>⚠ {item.citation}</b>
          <div>{item.notice.replace(/^⚠\s*تنبيه:\s*/, "")}</div>
        </div>
      ))}

      {reply.referrals.map((text, index) => (
        <div key={index} className="referral">
          {text}
        </div>
      ))}

      {/* When articles are quoted they already carry their citations. */}
      {reply.sources.length > 0 && reply.quoted.length === 0 && (
        <div className="sources">
          {reply.sources.map((source) => (
            <span key={source.number} className={source.amended ? "source amended-tag" : "source"}>
              {source.amended ? "" : source.number + " · "}
              {source.citation}
              {source.amended ? " · معدّلة" : ""}
            </span>
          ))}
        </div>
      )}
      <div className="meta">
        {reply.model} · {Math.round(reply.seconds)} ثانية
      </div>
    </div>
  );
}
