export default function EmptyState({ title, children, action }) {
  return (
    <section className="state-panel" aria-labelledby="empty-state-title">
      <p className="eyebrow">Quiet for now</p>
      <h2 id="empty-state-title">{title}</h2>
      {children ? <p>{children}</p> : null}
      {action}
    </section>
  );
}
