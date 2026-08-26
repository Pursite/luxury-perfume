export default function AuthLayout({ titleId, eyebrow, title, description, children }) {
  return (
    <div className="auth-layout page-frame">
      <div className="auth-editorial-mark" aria-hidden="true">LP / 01</div>
      <section className="auth-panel" aria-labelledby={titleId}>
        <div className="auth-introduction">
          <p className="eyebrow">{eyebrow}</p>
          <h1 id={titleId}>{title}</h1>
          <p>{description}</p>
          <span className="auth-introduction-rule" aria-hidden="true" />
          <span className="auth-introduction-caption">A quieter way to choose well.</span>
        </div>
        <div className="auth-form-column">{children}</div>
      </section>
    </div>
  );
}
