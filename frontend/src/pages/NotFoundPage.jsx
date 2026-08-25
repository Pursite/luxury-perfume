import { Link } from "react-router-dom";

import useDocumentTitle from "../hooks/useDocumentTitle";

export default function NotFoundPage() {
  useDocumentTitle("Page not found");
  return (
    <section className="not-found-page page-frame" aria-labelledby="not-found-title">
      <div className="not-found-number" aria-hidden="true">404</div>
      <div className="not-found-copy">
        <p className="eyebrow">Lost in the sillage</p>
        <h1 id="not-found-title">This trail ends here.</h1>
        <p>The page you followed does not exist or has moved elsewhere in the collection.</p>
        <Link className="button button-outline" to="/">Return to the collection</Link>
      </div>
    </section>
  );
}
