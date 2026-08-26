export default function ErrorState({ title, message, onRetry }) {
  return (
    <section className="state-panel state-panel-error" aria-labelledby="error-state-title">
      <p className="eyebrow">Connection interrupted</p>
      <h2 id="error-state-title">{title}</h2>
      <p>{message}</p>
      {onRetry ? (
        <button type="button" className="button button-outline" onClick={onRetry}>
          Try again
        </button>
      ) : null}
    </section>
  );
}
